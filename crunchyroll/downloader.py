"""Crunchyroll episode downloader using N_m3u8DL-RE + mp4decrypt.

Download pipeline:
  1. Fetch playback stream (MPD URL + token) via existing API functions
  2. Obtain Widevine decryption keys via existing drm.get_license()
  3. Call N_m3u8DL-RE which:
       - Downloads all DASH segments concurrently (video + audio tracks)
       - Calls mp4decrypt internally with the --key flags
       - Writes per-track decrypted MP4 files to a temp directory
  4. Download subtitles (.ass) via the existing HTTP helper
  5. FFmpeg-mux video + audio + subtitle tracks into the final .mkv
"""

import inspect
import os
import random
import shutil
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Callable, Dict, List, Optional, Tuple

import requests

from .api import delete_stream, get_episode, get_episode_download, get_episode_info, get_season_episodes, get_series
from .drm import get_license
from .http_client import CrunchyrollHttpClient
from .integrity import StreamValidator, atomic_finalize
from .merger import merge_everything
from .mpd import (
    get_pssh,
    parse_manifest,
)
from .session_pool import ConcurrencyConfig, SessionPool
from .tools import run_n_m3u8dl_re, find_n_m3u8dl_re, find_mp4decrypt
from .types import (
    DubVersion,
    EpisodeInfo,
    EpisodeMetadata,
    MediaTrack,
    PlaybackStream,
    SeasonEpisode,
)
from .utils import sanitize_filename, track_title


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _invoke_progress_cb(
    cb: Optional[Callable],
    title: str,
    completed: int,
    total: int,
    speed_str: str,
    speed_mb_s: float,
    status: str,
) -> None:
    """Invoke progress callback safely supporting various callback signatures."""
    if not cb:
        return
    try:
        sig = inspect.signature(cb)
        num_params = len(sig.parameters)
        if num_params == 5:
            cb(title, completed, total, speed_str, status)
        elif num_params == 3:
            cb(completed, total, speed_mb_s)
        elif num_params == 4:
            cb(title, completed, total, speed_str)
        else:
            cb(title, completed, total, speed_str, status)
    except (TypeError, ValueError):
        try:
            cb(title, completed, total, speed_str, status)
        except Exception:
            try:
                cb(completed, total, speed_mb_s)
            except Exception:
                pass


def download_subs(url: str, pool: Optional[SessionPool] = None) -> str:
    """Fetch a subtitle file and save it to a temporary .ass file."""
    if pool:
        content = pool.download_segment(url)
    else:
        resp = requests.get(
            url,
            headers={
                "Origin": "https://static.crunchyroll.com",
                "Referer": "https://static.crunchyroll.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
                ),
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.content
    tmp_file = tempfile.NamedTemporaryFile(suffix=".ass", delete=False)
    tmp_path = tmp_file.name
    tmp_file.write(content)
    tmp_file.close()
    return tmp_path


def _is_all_tracks(values: List[str]) -> bool:
    """Return whether a track selection requests every available track."""
    return any(value.strip().lower() in {"all", "*"} for value in values)


def _unique_locales(values: List[str]) -> List[str]:
    """Normalize a locale list while retaining its requested order."""
    result: List[str] = []
    seen = set()
    for value in values:
        locale = value.strip()
        key = locale.lower()
        if locale and key not in seen:
            result.append(locale)
            seen.add(key)
    return result


def _locale_map(values: Dict[str, object]) -> Dict[str, object]:
    """Index locale-keyed records case-insensitively."""
    return {key.strip().lower(): value for key, value in values.items() if key.strip()}


def _get_keys_for_stream(
    client: CrunchyrollHttpClient,
    ep: PlaybackStream,
    content_id: str,
    debug: bool,
) -> Dict[bytes, bytes]:
    """Fetch MPD and extract Widevine keys for a playback stream."""
    manifest = parse_manifest(client, ep.manifest_url, debug=debug)
    pssh = get_pssh(manifest)
    if not pssh:
        raise RuntimeError("PSSH not found in MPD manifest")
    return get_license(client, pssh, content_id, ep.token)


def _stream_expired_error(error: Exception) -> bool:
    """Return whether a media failure likely means signed playback URLs expired."""
    message = str(error).lower()
    return any(
        marker in message
        for marker in ("http 401", "http 403", "http 410", "unauthorized", "forbidden")
    )


def _cleanup_temp_dir(d: str) -> None:
    """Remove a temporary directory, ignoring errors."""
    try:
        shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API: episode / season / series
# ---------------------------------------------------------------------------

def download_episode(
    client: CrunchyrollHttpClient,
    base_content_id: str,
    info: EpisodeInfo,
    audio_langs: List[str],
    subs_langs: List[str],
    video_quality: str,
    audio_quality: str,
    debug: bool = False,
    progress_cb: Optional[Callable] = None,
    concurrency_config: Optional[ConcurrencyConfig] = None,
    force_download: bool = False,
    server_index: int = 0,
) -> str:
    """Download an episode using N_m3u8DL-RE and mux to MKV with FFmpeg.

    Flow:
      1. Resolve audio dub versions and output path (unchanged logic)
      2. Fetch playback stream tokens + MPD URLs via existing API
      3. Obtain Widevine keys from the license endpoint
      4. Call N_m3u8DL-RE once for the primary (video + all audio) stream
      5. For additional dub-only streams: call N_m3u8DL-RE audio-only
      6. Download subtitles via HTTP
      7. FFmpeg-mux into .mkv
    """
    # ------------------------------------------------------------------
    # 1. Resolve audio language list
    # ------------------------------------------------------------------
    audio_all = _is_all_tracks(audio_langs)
    subs_all = _is_all_tracks(subs_langs)

    if audio_all:
        audio_langs = _unique_locales(
            [v.audio_locale for v in info.episode_metadata.versions if v.audio_locale]
        )
        if not audio_langs:
            audio_langs = [info.episode_metadata.audio_locale or "ja-JP"]
        print(f"Available audio tracks: {', '.join(audio_langs)}")
    else:
        audio_langs = _unique_locales(audio_langs)

    versions_by_locale = {
        v.audio_locale.strip().lower(): v
        for v in info.episode_metadata.versions
        if v.audio_locale.strip()
    }
    versions: List[DubVersion] = []
    for loc in audio_langs:
        version = versions_by_locale.get(loc.lower())
        if version:
            versions.append(version)

    missing_audio = [
        locale for locale in audio_langs
        if locale.lower() not in {v.audio_locale.lower() for v in versions}
    ]

    if not versions:
        if info.episode_metadata.versions:
            versions.append(info.episode_metadata.versions[0])
        else:
            versions.append(
                DubVersion(
                    guid="",
                    media_guid="",
                    season_guid="",
                    audio_locale=info.episode_metadata.audio_locale or "ja-JP",
                    locale="",
                )
            )

    # ------------------------------------------------------------------
    # 2. Compute output file path
    # ------------------------------------------------------------------
    series_title = sanitize_filename(info.episode_metadata.series_title or "Unknown")
    ep_title = sanitize_filename(info.title or "Unknown")
    season_num = info.episode_metadata.season_number
    ep_num = info.episode_metadata.episode_number
    output_dir_base = os.path.join(".", series_title)
    os.makedirs(output_dir_base, exist_ok=True)
    output_filename = os.path.join(
        output_dir_base,
        f"{series_title} S{season_num:02d}E{ep_num:02d} - {ep_title} [{video_quality}].mkv",
    )

    if not force_download and os.path.exists(output_filename):
        print(f"Skipping (already downloaded): {output_filename}")
        return output_filename

    # ------------------------------------------------------------------
    # 3. Fetch playback streams and Widevine keys
    # ------------------------------------------------------------------
    active_streams: Dict[str, str] = {}
    playback_cache: Dict[str, PlaybackStream] = {}
    shared_pool = SessionPool(
        config=concurrency_config or ConcurrencyConfig(
            min_workers=4,
            max_workers=10,
            initial_workers=8,
        )
    )

    try:
        first_playback_id = versions[0].guid or base_content_id

        # Primary stream fetch
        first_episode = get_episode(
            client,
            first_playback_id,
            debug=debug,
            playback_id=first_playback_id,
            queue=0,
        )
        first_episode = get_episode_download(
            client,
            first_playback_id,
            play_stream=first_episode,
            debug=debug,
            client_type="android/phone",
        )
        playback_cache[first_playback_id] = first_episode
        active_streams[first_playback_id] = first_episode.token

        # ------------------------------------------------------------------
        # 4. Subtitle discovery (unchanged logic)
        # ------------------------------------------------------------------
        subtitle_map = _locale_map(first_episode.subtitles)
        primary_locale = (getattr(versions[0], "audio_locale", "") or "").lower()
        has_primary_subs = primary_locale == "ja-jp" and len(first_episode.subtitles) > 0

        if subs_all:
            needs_more_subs = not has_primary_subs and len(first_episode.subtitles) == 0
        else:
            needs_more_subs = any(loc.lower() not in subtitle_map for loc in subs_langs)

        if needs_more_subs:
            print("Fetching subtitles from versions...")
            candidate_versions = [
                v for v in info.episode_metadata.versions
                if v.guid and v.guid != first_playback_id
            ]
            candidate_versions.sort(
                key=lambda v: 0 if (getattr(v, "audio_locale", "") or "").lower() == "ja-jp" else 1
            )
            selected_audio_guids = {v.guid for v in versions if v.guid}

            for v_idx, version in enumerate(candidate_versions):
                print(f"Checking subtitle source: {track_title(version.audio_locale)}...")
                if v_idx > 0:
                    time.sleep(0.5)
                v_ep = get_episode(
                    client,
                    version.guid,
                    debug=debug,
                    playback_id=version.guid,
                    queue=1,
                )
                if version.guid in selected_audio_guids:
                    playback_cache[version.guid] = v_ep
                    active_streams[version.guid] = v_ep.token
                else:
                    if v_ep.token:
                        delete_stream(client, version.guid, v_ep.token)

                for locale, subtitle in v_ep.subtitles.items():
                    first_episode.subtitles.setdefault(locale, subtitle)

                subtitle_map = _locale_map(first_episode.subtitles)
                if not subs_all and all(loc.lower() in subtitle_map for loc in subs_langs):
                    break
                if (getattr(version, "audio_locale", "") or "").lower() == "ja-jp" and v_ep.subtitles:
                    break
                if v_idx >= 1 and first_episode.subtitles:
                    break

            if not first_episode.subtitles:
                print("Warning: Failed to fetch subtitles!")

        subtitle_map = _locale_map(first_episode.subtitles)
        if subs_all:
            subs_langs = _unique_locales(list(first_episode.subtitles.keys()))
        else:
            subs_langs = _unique_locales(subs_langs)

        available_subtitles = list(subtitle_map)
        missing_subtitles = [
            locale for locale in subs_langs
            if locale.lower() not in {a.lower() for a in available_subtitles}
        ]
        print(
            "Tracks selected: "
            f"audio=[{', '.join(track_title(v.audio_locale) for v in versions) or 'none'}], "
            f"subtitles=[{', '.join(track_title(loc) for loc in subs_langs) or 'none'}]"
        )
        if missing_audio:
            print(f"Warning: Audio tracks unavailable: {', '.join(missing_audio)}")
        if missing_subtitles:
            print(f"Warning: Subtitle tracks unavailable: {', '.join(missing_subtitles)}")

        # ------------------------------------------------------------------
        # 5. Download subtitles
        # ------------------------------------------------------------------
        sub_tracks: List[MediaTrack] = []
        for loc in subs_langs:
            subtitle = subtitle_map.get(loc.lower())
            if subtitle and subtitle.url:
                actual_locale = getattr(subtitle, "language", None) or loc
                print(f"Downloading subtitles for {track_title(actual_locale)}...")
                sub_file = download_subs(subtitle.url, pool=shared_pool)
                sub_tracks.append(
                    MediaTrack(file=sub_file, locale=actual_locale, is_default=len(sub_tracks) == 0)
                )

        if sub_tracks:
            print(
                "Downloaded subtitles: "
                + ", ".join(
                    f"{track_title(t.locale)}" + (" (default)" if t.is_default else "")
                    for t in sub_tracks
                )
            )
        elif subs_langs:
            print("Downloaded subtitles: none")

        # ------------------------------------------------------------------
        # 6. Download video + audio with N_m3u8DL-RE
        # ------------------------------------------------------------------
        _invoke_progress_cb(progress_cb, info.title, 0, 1, "", 0.0, "downloading")

        video_file: Optional[str] = None
        audio_tracks: List[MediaTrack] = []

        # Sanitized base name for file outputs
        base_name = sanitize_filename(
            f"{series_title}_S{season_num:02d}E{ep_num:02d}"
        )

        # Primary stream: video + first audio dub
        primary_content_id = versions[0].guid or base_content_id
        primary_ep = playback_cache[primary_content_id]

        # Get Widevine keys for the primary stream
        print("Fetching Widevine license keys...")
        primary_keys = _get_keys_for_stream(client, primary_ep, primary_content_id, debug)
        if not primary_keys:
            raise RuntimeError("No Widevine keys returned from license server")

        # Temp dir for N_m3u8DL-RE output
        primary_tmp = tempfile.mkdtemp(prefix="crunrun_primary_")
        try:
            print("Downloading video + primary audio with N_m3u8DL-RE...")
            result = run_n_m3u8dl_re(
                mpd_url=primary_ep.manifest_url,
                keys=primary_keys,
                output_dir=primary_tmp,
                base_name=base_name,
                bearer_token=client.token or "",
                video_quality=video_quality,
                mp4decrypt_path=None,  # auto-detect from bin/
            )

            video_file = result["video"]
            primary_audio_files: List[str] = result.get("audio_files", [])

        except Exception as exc:
            _cleanup_temp_dir(primary_tmp)
            raise RuntimeError(f"Primary stream download failed: {exc}") from exc

        # Map each audio file to a locale using N_m3u8DL-RE naming convention.
        # N_m3u8DL-RE names audio tracks like: <base>_audio_<lang>.mp4 or <base>_1.mp4 etc.
        # We match them to our requested locales as best we can.
        primary_audio_locale = versions[0].audio_locale if versions else "ja-JP"
        if primary_audio_files:
            # First audio file = primary dub
            audio_tracks.append(MediaTrack(
                file=primary_audio_files[0],
                locale=primary_audio_locale,
                is_default=True,
            ))
            # Additional audio tracks from the same stream (if any) — match by index to remaining versions
            for extra_idx, extra_file in enumerate(primary_audio_files[1:], start=1):
                extra_locale = versions[extra_idx].audio_locale if extra_idx < len(versions) else primary_audio_locale
                audio_tracks.append(MediaTrack(
                    file=extra_file,
                    locale=extra_locale,
                    is_default=False,
                ))
        elif video_file:
            # N_m3u8DL-RE may embed audio in the video file; FFmpeg will pick it up
            print("Note: no separate audio file found; audio may be muxed in the video track.")

        # Additional dub streams (separate GUID/MPD per extra language version)
        already_covered = {a.locale.lower() for a in audio_tracks}
        for i, version in enumerate(versions[1:], start=1):
            if version.audio_locale.lower() in already_covered:
                print(f"Skipping {track_title(version.audio_locale)}: already covered by primary stream")
                continue

            dub_content_id = version.guid or base_content_id
            dub_ep = playback_cache.get(dub_content_id)
            if dub_ep is None:
                dub_ep = get_episode(client, dub_content_id, debug=debug, playback_id=dub_content_id, queue=1)
                dub_ep = get_episode_download(client, dub_content_id, play_stream=dub_ep, debug=debug, client_type="android/phone")
                playback_cache[dub_content_id] = dub_ep
                active_streams[dub_content_id] = dub_ep.token

            print(f"Fetching Widevine keys for {track_title(version.audio_locale)}...")
            dub_keys = _get_keys_for_stream(client, dub_ep, dub_content_id, debug)
            if not dub_keys:
                print(f"Warning: No keys for {track_title(version.audio_locale)}, skipping.")
                continue

            dub_tmp = tempfile.mkdtemp(prefix=f"crunrun_dub{i}_")
            dub_base = f"{base_name}_dub{i}"
            try:
                print(f"Downloading {track_title(version.audio_locale)} audio with N_m3u8DL-RE...")
                dub_result = run_n_m3u8dl_re(
                    mpd_url=dub_ep.manifest_url,
                    keys=dub_keys,
                    output_dir=dub_tmp,
                    base_name=dub_base,
                    bearer_token=client.token or "",
                    audio_only=True,  # dub streams: video track not needed
                    mp4decrypt_path=None,
                )
                dub_audio_files = dub_result.get("audio_files", [])
                if not dub_audio_files and dub_result.get("video"):
                    # If no dedicated audio file, the video file contains the audio
                    dub_audio_files = [dub_result["video"]]

                if dub_audio_files:
                    audio_tracks.append(MediaTrack(
                        file=dub_audio_files[0],
                        locale=version.audio_locale,
                        is_default=False,
                    ))
                    already_covered.add(version.audio_locale.lower())
                    print(f"Downloaded audio: {track_title(version.audio_locale)}")
                else:
                    print(f"Warning: No audio file produced for {track_title(version.audio_locale)}")
                    _cleanup_temp_dir(dub_tmp)
            except Exception as exc:
                print(f"Warning: Failed to download {track_title(version.audio_locale)} audio: {exc}")
                _cleanup_temp_dir(dub_tmp)

            # Release secondary stream session to avoid hitting concurrent playback limit
            token_to_del = active_streams.pop(dub_content_id, None)
            if token_to_del:
                delete_stream(client, dub_content_id, token_to_del)

        if not video_file:
            raise RuntimeError("No video file was produced by N_m3u8DL-RE!")

        # ------------------------------------------------------------------
        # 7. Mux everything into .mkv
        # ------------------------------------------------------------------
        _invoke_progress_cb(progress_cb, info.title, 1, 1, "", 0.0, "muxing")

        print("Muxing tracks into MKV...")
        temp_output_filename = output_filename + ".tmp.mkv"
        merge_everything(
            video_file=video_file,
            audio_tracks=audio_tracks,
            sub_tracks=sub_tracks,
            output_file=temp_output_filename,
            info=info,
        )

        try:
            is_valid, msg, _ = StreamValidator.verify_mkv(
                temp_output_filename,
                expected_video=True,
                min_audio_tracks=len(audio_tracks),
                min_sub_tracks=len(sub_tracks),
            )
            if not is_valid:
                if os.path.exists(temp_output_filename):
                    try:
                        os.remove(temp_output_filename)
                    except OSError:
                        pass
                raise RuntimeError(f"Output MKV failed integrity verification: {msg}")
        except FileNotFoundError:
            pass

        atomic_finalize(temp_output_filename, output_filename)
        print(
            "\nTracks in output: "
            f"audio=[{', '.join(track_title(t.locale) + (' (default)' if t.is_default else '') for t in audio_tracks)}], "
            f"subtitles=[{', '.join(track_title(t.locale) + (' (default)' if t.is_default else '') for t in sub_tracks) or 'none'}]"
        )
        print(f"Download finished! Output file: {output_filename}\n")
        return output_filename

    finally:
        shared_pool.close()
        print("Cleaning up streams...")
        for content_id, token in active_streams.items():
            if content_id and token:
                delete_stream(client, content_id, token)
        # Clean up temp dirs from N_m3u8DL-RE runs (they live in system temp)
        # Individual dub temp dirs that failed are already cleaned above


def download_season(
    client: CrunchyrollHttpClient,
    video_quality: str,
    audio_quality: str,
    audio_langs: List[str],
    subs_langs: List[str],
    episodes: List[SeasonEpisode],
    debug: bool = False,
    progress_cb: Optional[Callable] = None,
    concurrency_config: Optional[ConcurrencyConfig] = None,
    force_download: bool = False,
    server_index: int = 0,
) -> None:
    """Download an entire season."""
    print(f"Found {len(episodes)} episodes in this season!\n")
    for i, ep in enumerate(episodes):
        if i > 0:
            time.sleep(random.uniform(1.5, 3.0))
        print(f"=== [{i+1}/{len(episodes)}] {ep.title} ===")
        episode_versions = ep.versions
        needed_locales = {loc.strip().lower() for loc in audio_langs if loc.strip()}
        existing_locales = {v.audio_locale.strip().lower() for v in episode_versions if getattr(v, "audio_locale", None)}
        if ep.id and (_is_all_tracks(audio_langs) or not needed_locales.issubset(existing_locales)):
            try:
                episode_info = get_episode_info(client, ep.id)
                if episode_info.episode_metadata.versions:
                    episode_versions = episode_info.episode_metadata.versions
            except Exception as exc:
                print(f"Warning: Failed to discover all audio versions: {exc}")

        info = EpisodeInfo(
            episode_metadata=EpisodeMetadata(
                series_title=ep.series_title,
                season_number=ep.season_number,
                episode_number=ep.episode_number,
                audio_locale=ep.audio_locale,
                versions=episode_versions,
                availability_starts=ep.availability_starts,
            ),
            title=ep.title,
        )
        download_episode(
            client,
            ep.id,
            info,
            audio_langs,
            subs_langs,
            video_quality,
            audio_quality,
            debug=debug,
            progress_cb=progress_cb,
            concurrency_config=concurrency_config,
            force_download=force_download,
            server_index=server_index,
        )
        print()


def download_series(
    client: CrunchyrollHttpClient,
    series_id: str,
    audio_langs: List[str],
    subs_langs: List[str],
    video_quality: str,
    audio_quality: str,
    season_filter: int = 0,
    progress_cb: Optional[Callable] = None,
    debug: bool = False,
    concurrency_config: Optional[ConcurrencyConfig] = None,
    force_download: bool = False,
    server_index: int = 0,
) -> None:
    """Download all episodes for a series."""
    primary_audio = (
        audio_langs[0]
        if audio_langs and not _is_all_tracks(audio_langs)
        else "ja-JP"
    )
    primary_subs = (
        subs_langs[0]
        if subs_langs and not _is_all_tracks(subs_langs)
        else "en-US"
    )

    series_data = get_series(client, series_id, primary_audio, primary_subs)
    episodes = series_data.get("episodes", [])

    if season_filter > 0:
        episodes = [ep for ep in episodes if ep.season_number == season_filter]
        if not episodes:
            print(f"No episodes found for season {season_filter}.")
            return

    print(
        f"Downloading series '{series_data.get('title', series_id)}' "
        f"({len(episodes)} episodes across {len(series_data.get('seasons', []))} seasons)\n"
    )

    for i, ep in enumerate(episodes):
        if i > 0:
            time.sleep(random.uniform(1.5, 3.0))
        print(f"=== [{i+1}/{len(episodes)}] {ep.series_title} S{ep.season_number:02d}E{ep.episode_number:02d} - {ep.title} ===")
        episode_versions = ep.versions
        needed_locales = {loc.strip().lower() for loc in audio_langs if loc.strip()}
        existing_locales = {v.audio_locale.strip().lower() for v in episode_versions if getattr(v, "audio_locale", None)}
        if ep.id and (_is_all_tracks(audio_langs) or not needed_locales.issubset(existing_locales)):
            try:
                episode_info = get_episode_info(client, ep.id)
                if episode_info.episode_metadata.versions:
                    episode_versions = episode_info.episode_metadata.versions
            except Exception as exc:
                print(f"Warning: Failed to discover all audio versions: {exc}")

        info = EpisodeInfo(
            episode_metadata=EpisodeMetadata(
                series_title=ep.series_title,
                season_number=ep.season_number,
                episode_number=ep.episode_number,
                audio_locale=ep.audio_locale,
                versions=episode_versions,
                availability_starts=ep.availability_starts,
            ),
            title=ep.title,
        )

        download_episode(
            client,
            ep.id,
            info,
            audio_langs,
            subs_langs,
            video_quality,
            audio_quality,
            debug=debug,
            progress_cb=progress_cb,
            concurrency_config=concurrency_config,
            force_download=force_download,
            server_index=server_index,
        )
        print()
