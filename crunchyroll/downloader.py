import inspect
import os
import queue
import shutil
import subprocess
import random
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple, Union

import requests

from .api import delete_stream, get_episode, get_episode_info, get_season_episodes, get_series
from .decryptor import decrypt_mp4, decrypt_stream
from .drm import get_license
from .http_client import CrunchyrollHttpClient
from .integrity import StreamValidator, atomic_finalize
from .merger import find_ffmpeg, merge_everything
from .mpd import (
    expand_timeline,
    get_base_url,
    get_kids,
    get_pssh,
    parse_dash_duration,
    parse_manifest,
)
from .session_pool import ConcurrencyConfig, SessionPool
from .stream_assembler import StreamAssembler
from .types import (
    DubVersion,
    EpisodeInfo,
    EpisodeMetadata,
    MediaTrack,
    PlaybackStream,
    SeasonEpisode,
)
from .utils import sanitize_filename, track_title

MAX_WORKERS = 8
MAX_RETRIES = 5
BACKOFF_FACTOR = 1.5

_GLOBAL_SESSION_POOL: Optional[SessionPool] = None
_GLOBAL_POOL_LOCK = threading.Lock()


def _get_global_session_pool() -> SessionPool:
    global _GLOBAL_SESSION_POOL
    with _GLOBAL_POOL_LOCK:
        if _GLOBAL_SESSION_POOL is None:
            _GLOBAL_SESSION_POOL = SessionPool(
                config=ConcurrencyConfig(
                    pool_size=16,
                    min_workers=4,
                    max_workers=8,
                    initial_workers=6,
                )
            )
        return _GLOBAL_SESSION_POOL


def _clean_tag(tag: str) -> str:
    """strip xml namespace prefix"""
    return tag.split("}")[-1] if "}" in tag else tag


def build_url(
    base_url: str, representation_id: str, pattern: str, number: Optional[int] = None
) -> str:
    """build the segment url like the go version does"""
    res = pattern
    if number is not None:
        formatted_num = f"{number:05d}"
        res = res.replace("$Number%05d$", formatted_num)
        res = res.replace("$Number$", formatted_num)
    res = res.replace("$RepresentationID$", representation_id)
    return base_url + res


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


def download_part(
    url: str,
    save_path: Optional[str] = None,
    max_retries: int = MAX_RETRIES,
    pool: Optional[SessionPool] = None,
) -> Union[bytes, int]:
    """grab a segment directly to disk or memory. retry if cr gets mad."""
    session_pool = pool or _get_global_session_pool()

    headers = {
        "Origin": "https://static.crunchyroll.com",
        "Referer": "https://static.crunchyroll.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    }

    if save_path:
        written = 0
        with open(save_path, "wb") as f:
            for chunk in session_pool.download_segment_stream(url, headers=headers):
                f.write(chunk)
                written += len(chunk)
        return written
    else:
        return session_pool.download_segment(url, headers=headers)


# decrypt_mp4 and decrypt_stream are imported from crunchyroll.decryptor


def download_parts(
    base_url: str,
    representation_id: str,
    adaptation_set: ET.Element,
    keys: Dict[bytes, bytes],
    ep_title: str = "",
    progress_cb: Optional[Callable] = None,
    pool: Optional[SessionPool] = None,
    concurrency_config: Optional[ConcurrencyConfig] = None,
    track_type: str = "video",
    period_duration_seconds: Optional[float] = None,
) -> str:
    """Download all track segments using high-performance streaming assembly and session pool."""
    # SegmentTemplate may be inherited from AdaptationSet, Representation,
    # or a parent Period/MPD. Use the same descendant resolution as the
    # timeline parser so URL patterns and segment counts cannot disagree.
    seg_template = next(
        (elem for elem in adaptation_set.iter() if _clean_tag(elem.tag) == "SegmentTemplate"),
        None,
    )

    init_file = seg_template.attrib.get("initialization", "") if seg_template is not None else ""
    media_file = seg_template.attrib.get("media", "") if seg_template is not None else ""

    timeline = expand_timeline(
        adaptation_set,
        period_duration_seconds=period_duration_seconds,
    )
    total = len(timeline)

    # Use existing session pool or create a new dedicated instance
    own_pool = False
    if pool is None:
        cfg = concurrency_config or ConcurrencyConfig(
            min_workers=4,
            max_workers=8,
            initial_workers=6,
            aimd_enabled=True,
            hedging_enabled=False,
        )
        pool = SessionPool(config=cfg)
        own_pool = True

    try:
        # Create raw output path
        raw_tmp = tempfile.NamedTemporaryFile(suffix=".raw.mp4", delete=False)
        raw_path = raw_tmp.name
        raw_tmp.close()

        # Handle direct single-file streams (e.g. Blue Lock SegmentBase with direct BaseURL)
        if total == 0:
            media_url = build_url(base_url, representation_id, init_file) if init_file else base_url
            headers = {
                "Origin": "https://static.crunchyroll.com",
                "Referer": "https://static.crunchyroll.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
            }
            chunk_size = 512 * 1024

            def _file_progress(completed_bytes: int, total_bytes: int, speed_mb_s: float) -> None:
                if total_bytes > 0:
                    percent = min(100.0, completed_bytes * 100.0 / total_bytes)
                    progress_text = (
                        f"\rDownloading {track_type}: {completed_bytes / (1024 * 1024):.1f} / "
                        f"{total_bytes / (1024 * 1024):.1f} MB ({percent:5.1f}%) "
                        f"[{speed_mb_s:.2f} MB/s]"
                    )
                    callback_total = total_bytes
                else:
                    progress_text = (
                        f"\rDownloading {track_type}: {completed_bytes / (1024 * 1024):.1f} MB "
                        f"[{speed_mb_s:.2f} MB/s]"
                    )
                    callback_total = 0
                try:
                    print(progress_text, end="", flush=True)
                except Exception:
                    pass
                if progress_cb:
                    _invoke_progress_cb(
                        progress_cb,
                        ep_title,
                        completed_bytes,
                        callback_total,
                        f"{speed_mb_s:.2f} MB/s",
                        speed_mb_s,
                        f"{track_type}-file",
                    )

            total_bytes = 0
            start_time = time.time()
            total_bytes = pool.download_file_stream(
                media_url,
                raw_path,
                headers=headers,
                timeout=30,
                chunk_size=chunk_size,
                progress_callback=_file_progress,
                parallel_ranges=8,
                range_size=4 * 1024 * 1024,
            )
            elapsed = time.time() - start_time
            speed_mb = total_bytes / max(elapsed, 0.001) / (1024 * 1024)
            speed_str = f"{speed_mb:.2f} MB/s"
            _invoke_progress_cb(
                progress_cb,
                ep_title,
                total_bytes,
                total_bytes,
                speed_str,
                speed_mb,
                f"{track_type}-file",
            )

            if sys.stdout is not None:
                try:
                    print("\nFinished downloading!")
                except Exception:
                    pass

            # Probe the complete encrypted source before decryption. This is
            # essential for SegmentBase manifests, where one BaseURL is the
            # entire fMP4 rather than a list of independently checked parts.
            StreamValidator.log_timing(raw_path, f"{track_type} encrypted source")

            decrypted_tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            decrypted_path = decrypted_tmp.name
            decrypted_tmp.close()

            decrypt_mp4(raw_path, keys, decrypted_path)
            StreamValidator.log_timing(decrypted_path, f"{track_type} decrypted")
            if os.path.exists(raw_path):
                try:
                    os.remove(raw_path)
                except Exception:
                    pass

            return decrypted_path

        # Step 1: Download and write initialization segment directly
        init_url = build_url(base_url, representation_id, init_file)
        init_data = pool.download_segment(init_url)

        # Step 2: Initialize bounded streaming assembler (< 32 MB RAM)
        assembler = StreamAssembler(
            output_path=raw_path,
            total_segments=total,
            max_in_flight_mb=32,
            start_index=1,
        )
        assembler.write_init(init_data)

        # Step 3: Concurrent segment downloading with AIMD dynamic worker scaling
        job_queue: queue.Queue = queue.Queue()
        for i, item in enumerate(timeline, start=1):
            seg_url = build_url(base_url, representation_id, media_file, item)
            job_queue.put((i, seg_url))

        completed_count = 0
        downloaded_bytes = 0
        start_time = time.time()
        progress_lock = threading.Lock()
        worker_error: List[Exception] = []
        active_requests = 0

        max_allowed_workers = pool.config.max_workers

        def _worker_loop():
            nonlocal completed_count, downloaded_bytes, active_requests
            while not job_queue.empty() and not worker_error:
                try:
                    idx, url = job_queue.get_nowait()
                except queue.Empty:
                    break

                try:
                    with progress_lock:
                        active_requests += 1
                    seg_data = pool.download_segment(url)
                    assembler.add_segment(idx, seg_data)

                    with progress_lock:
                        active_requests -= 1
                        completed_count += 1
                        downloaded_bytes += len(seg_data)
                        cur_completed = completed_count
                        cur_bytes = downloaded_bytes

                    elapsed = time.time() - start_time
                    speed_mb = (cur_bytes / elapsed / (1024 * 1024)) if elapsed > 0 else 0.0
                    speed_str = f"{speed_mb:.2f} MB/s"
                    percent = (100 * cur_completed) // total if total > 0 else 100

                    if sys.stdout is not None:
                        try:
                            sys.stdout.write(
                                f"\rDownloaded {cur_completed} of {total} segments ({percent}%) "
                                f"[{speed_str}; {active_requests} active]"
                            )
                            sys.stdout.flush()
                        except Exception:
                            pass

                    _invoke_progress_cb(
                        progress_cb,
                        ep_title,
                        cur_completed,
                        total,
                        speed_str,
                        speed_mb,
                        track_type,
                    )
                except Exception as ex:
                    with progress_lock:
                        active_requests = max(0, active_requests - 1)
                        worker_error.append(ex)
                        failed_count = completed_count
                    print(
                        f"\nDownload failed for {track_type} segment {idx}/{total} "
                        f"after {failed_count} completed: {type(ex).__name__}: {ex}"
                    )
                    assembler.abort(ex)
                    _invoke_progress_cb(
                        progress_cb,
                        ep_title,
                        completed_count,
                        total,
                        "0 MB/s",
                        0.0,
                        "failed",
                    )
                    break
                finally:
                    job_queue.task_done()

        # Spawn worker threads dynamically
        num_workers = min(total, max(pool.config.min_workers, pool.get_recommended_workers()))
        threads: List[threading.Thread] = []
        for _ in range(num_workers):
            t = threading.Thread(target=_worker_loop, daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        if worker_error:
            if sys.stdout is not None:
                try:
                    print()
                except Exception:
                    pass
            raise worker_error[0]

        try:
            if sys.stdout is not None:
                print("\nFinished downloading!")
        except Exception:
            pass

        # Finalize raw stream sequential assembly
        assembler.finish()

        # Step 4: Decrypt raw MP4 to decrypted output temp file
        StreamValidator.log_timing(raw_path, f"{track_type} encrypted source")
        decrypted_tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        decrypted_path = decrypted_tmp.name
        decrypted_tmp.close()

        decrypt_mp4(raw_path, keys, decrypted_path)
        StreamValidator.log_timing(decrypted_path, f"{track_type} decrypted")
        if os.path.exists(raw_path):
            try:
                os.remove(raw_path)
            except Exception:
                pass

        return decrypted_path

    finally:
        if own_pool and pool:
            pool.close()


def download_parts_optimized(
    base_url: str,
    rep_id: str,
    timeline: List[int],
    keys: Optional[Dict[bytes, bytes]],
    output_filename: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
    concurrency_config: Optional[ConcurrencyConfig] = None,
    media_pattern: str = "$RepresentationID$_segment_$Number$.mp4",
    init_pattern: str = "$RepresentationID$_init.mp4",
) -> str:
    """Optimized download pipeline API interface matching PROJECT.md interface contract."""
    cfg = concurrency_config or ConcurrencyConfig(
        min_workers=6,
        max_workers=16,
        initial_workers=12,
        aimd_enabled=True,
        hedging_enabled=False,
    )
    pool = SessionPool(config=cfg)

    target_raw = output_filename + ".raw.mp4" if output_filename else tempfile.NamedTemporaryFile(suffix=".raw.mp4", delete=False).name
    target_out = output_filename or tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name

    total = len(timeline)
    try:
        # Step 1: Download init segment
        init_url = build_url(base_url, rep_id, init_pattern)
        init_data = pool.download_segment(init_url)

        # Step 2: StreamAssembler (<32MB RAM)
        assembler = StreamAssembler(
            output_path=target_raw,
            total_segments=total,
            max_in_flight_mb=32,
            start_index=1,
        )
        assembler.write_init(init_data)

        # Step 3: Concurrent download
        job_queue: queue.Queue = queue.Queue()
        for i, item in enumerate(timeline, start=1):
            seg_url = build_url(base_url, rep_id, media_pattern, item)
            job_queue.put((i, seg_url))

        completed_count = 0
        downloaded_bytes = 0
        start_time = time.time()
        progress_lock = threading.Lock()
        worker_error: List[Exception] = []

        def _worker():
            nonlocal completed_count, downloaded_bytes
            while not job_queue.empty() and not worker_error:
                try:
                    idx, url = job_queue.get_nowait()
                except queue.Empty:
                    break

                try:
                    seg_data = pool.download_segment(url)
                    assembler.add_segment(idx, seg_data)

                    with progress_lock:
                        completed_count += 1
                        downloaded_bytes += len(seg_data)
                        cur_completed = completed_count
                        cur_bytes = downloaded_bytes

                    elapsed = time.time() - start_time
                    speed_mb = (cur_bytes / elapsed / (1024 * 1024)) if elapsed > 0 else 0.0

                    if progress_callback:
                        progress_callback(cur_completed, total, speed_mb)
                except Exception as ex:
                    with progress_lock:
                        worker_error.append(ex)
                    print(
                        f"\nDownload failed for optimized segment {idx}/{total}: "
                        f"{type(ex).__name__}: {ex}"
                    )
                    assembler.abort(ex)
                    break
                finally:
                    job_queue.task_done()

        num_workers = min(total, max(cfg.min_workers, pool.get_recommended_workers()))
        threads = [threading.Thread(target=_worker, daemon=True) for _ in range(num_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if worker_error:
            raise worker_error[0]

        assembler.finish()

        # Step 4: Decrypt
        decrypt_mp4(target_raw, keys or {}, target_out)
        if os.path.exists(target_raw):
            try:
                os.remove(target_raw)
            except Exception:
                pass

        return target_out
    finally:
        pool.close()


def download_subs(url: str, pool: Optional[SessionPool] = None) -> str:
    """grab subs and stash in a temp file"""
    session_pool = pool or _get_global_session_pool()
    content = session_pool.download_segment(url)
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


def _keys_for_adaptation_set(
    keys: Dict[bytes, bytes], adaptation_set: Optional[ET.Element]
) -> Dict[bytes, bytes]:
    """Return license keys matching all CENC KIDs in an adaptation set."""
    if not keys or adaptation_set is None:
        return keys
    kids = get_kids(adaptation_set)
    if not kids:
        return keys
    normalized_keys = {}
    for candidate, value in keys.items():
        candidate_bytes = bytes(candidate).lower()
        normalized_keys[candidate_bytes] = (candidate, value)
        if len(candidate_bytes) == 16:
            normalized_keys.setdefault(
                uuid.UUID(bytes=candidate_bytes).bytes_le,
                (candidate, value),
            )
    selected = {}
    missing = []
    for kid in kids:
        kid_bytes = bytes(kid).lower()
        match = normalized_keys.get(kid_bytes)
        if match is None and len(kid_bytes) == 16:
            match = normalized_keys.get(uuid.UUID(bytes=kid_bytes).bytes_le)
        if match is None:
            missing.append(kid.hex())
        else:
            selected[match[0]] = match[1]
    if missing:
        print(
            "Warning: Exact adaptation-set KID(s) not matched in license keys, "
            f"falling back to all keys: {', '.join(missing)}"
        )
        return keys
    return selected


def _stream_expired_error(error: Exception) -> bool:
    """Return whether a media failure likely means signed playback URLs expired."""
    message = str(error).lower()
    return any(
        marker in message
        for marker in ("http 401", "http 403", "http 410", "unauthorized", "forbidden")
    )


def _prepare_media_track(
    client: CrunchyrollHttpClient,
    ep: PlaybackStream,
    content_id: str,
    audio_quality: str,
    video_quality: str,
    debug: bool,
) -> Dict[str, object]:
    """Fetch a current MPD and license keys and resolve its media sets."""
    manifest = parse_manifest(client, ep.manifest_url, debug=debug)
    pssh = get_pssh(manifest)
    if not pssh:
        raise RuntimeError("PSSH not found in MPD manifest")

    keys = get_license(client, pssh, content_id, ep.token)
    periods = [e for e in manifest if _clean_tag(e.tag) == "Period"]
    period = periods[0] if periods else manifest
    period_duration_seconds = parse_dash_duration(period.attrib.get("duration"))
    if period_duration_seconds is None:
        period_duration_seconds = parse_dash_duration(
            manifest.attrib.get("mediaPresentationDuration")
        )
    adaptation_sets = [e for e in period if _clean_tag(e.tag) == "AdaptationSet"]

    video_set = None
    audio_set = None
    for aset in adaptation_sets:
        mime = aset.attrib.get("mimeType", "")
        ctype = aset.attrib.get("contentType", "")
        reps = [r for r in aset if _clean_tag(r.tag) == "Representation"]
        is_video = "video" in mime or "video" in ctype or any(
            "height" in r.attrib for r in reps
        )
        is_audio = "audio" in mime or "audio" in ctype or any(
            "audio" in r.attrib.get("id", "") for r in reps
        )
        if is_video and video_set is None:
            video_set = aset
        elif is_audio and audio_set is None:
            audio_set = aset

    if audio_set is None and len(adaptation_sets) > 1:
        audio_set = adaptation_sets[1]
    if video_set is None and adaptation_sets:
        video_set = adaptation_sets[0]

    audio_base_url, audio_rep_id = get_base_url(audio_set, False, audio_quality)
    if not audio_base_url or not audio_rep_id:
        raise RuntimeError("failed to get the audio base URL")
    video_base_url, video_rep_id = get_base_url(video_set, True, video_quality)
    if not video_base_url or not video_rep_id:
        raise RuntimeError("failed to get the video base URL")

    return {
        "audio_set": audio_set,
        "audio_keys": _keys_for_adaptation_set(keys, audio_set),
        "audio_base_url": audio_base_url,
        "audio_rep_id": audio_rep_id,
        "video_set": video_set,
        "video_keys": _keys_for_adaptation_set(keys, video_set),
        "video_base_url": video_base_url,
        "video_rep_id": video_rep_id,
        "period_duration_seconds": period_duration_seconds,
    }


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
) -> str:
    """download all streams for an episode and mux to mkv using shared session pooling"""
    audio_all = _is_all_tracks(audio_langs)
    subs_all = _is_all_tracks(subs_langs)

    if audio_all:
        audio_langs = _unique_locales(
            [version.audio_locale for version in info.episode_metadata.versions if version.audio_locale]
        )
        if not audio_langs:
            audio_langs = [info.episode_metadata.audio_locale or "ja-JP"]
        print(f"Available audio tracks: {', '.join(audio_langs)}")
    else:
        audio_langs = _unique_locales(audio_langs)

    versions: List[DubVersion] = []
    versions_by_locale = {
        version.audio_locale.strip().lower(): version
        for version in info.episode_metadata.versions
        if version.audio_locale.strip()
    }
    for loc in audio_langs:
        version = versions_by_locale.get(loc.lower())
        if version:
            versions.append(version)

    missing_audio = [
        locale for locale in audio_langs
        if locale.lower() not in {version.audio_locale.lower() for version in versions}
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
                    audio_locale=info.episode_metadata.audio_locale,
                    locale="",
                )
            )

    active_streams: Dict[str, str] = {}
    playback_cache: Dict[str, PlaybackStream] = {}
    print(
        f"Downloading: {info.title} (S{info.episode_metadata.season_number:02d}E{info.episode_metadata.episode_number:02d}) from {info.episode_metadata.series_title}"
    )
    print(
        "Tracks planned: "
        f"audio=[{', '.join(track_title(version.audio_locale) for version in versions)}], "
        f"subtitles=[{', '.join(track_title(locale) for locale in subs_langs) or 'all available'}]"
    )

    output_dir = sanitize_filename(info.episode_metadata.series_title)
    os.makedirs(output_dir, exist_ok=True)
    filename = (
        f"{sanitize_filename(info.episode_metadata.series_title)} "
        f"S{info.episode_metadata.season_number:02d}E{info.episode_metadata.episode_number:02d} - "
        f"{sanitize_filename(info.title)} [{video_quality}].mkv"
    )
    output_filename = os.path.join(output_dir, filename)

    # Check completed output before making playback/subtitle requests. This
    # avoids network work, and avoids hanging on an episode already downloaded.
    if os.path.exists(output_filename) and not force_download:
        sz = os.path.getsize(output_filename)
        if sz > 10 * 1024 * 1024:
            print(f"Skipping (file already exists): {output_filename} ({sz / (1024*1024):.1f} MB)")
            return output_filename
        print(f"Existing file is corrupted/partial ({sz} bytes), re-downloading...")
        try:
            os.remove(output_filename)
        except Exception:
            pass
    elif os.path.exists(output_filename) and force_download:
        print(f"Force download enabled; replacing existing file: {output_filename}")

    # Initialize shared SessionPool across all tracks for connection reuse
    shared_pool = SessionPool(
        config=concurrency_config
        or ConcurrencyConfig(
            pool_size=16,
            min_workers=4,
            max_workers=8,
            initial_workers=6,
            aimd_enabled=True,
            hedging_enabled=False,
        )
    )

    try:
        print("Requesting playback stream...")
        first_playback_id = versions[0].guid or base_content_id
        first_episode = get_episode(
            client,
            first_playback_id,
            debug=debug,
            playback_id=first_playback_id,
        )
        playback_cache[first_playback_id] = first_episode
        active_streams[first_playback_id] = first_episode.token

        subtitle_map = _locale_map(first_episode.subtitles)
        needs_more_subs = subs_all or any(loc.lower() not in subtitle_map for loc in subs_langs)
        if needs_more_subs:
            print("Fetching subtitles from versions...")
            for version in info.episode_metadata.versions:
                if version.guid and version.guid != first_playback_id:
                    print(f"Checking subtitle source: {track_title(version.audio_locale)}...")
                    v_ep = get_episode(
                        client,
                        version.guid,
                        debug=debug,
                        playback_id=version.guid,
                    )
                    playback_cache[version.guid] = v_ep
                    active_streams[version.guid] = v_ep.token
                    for locale, subtitle in v_ep.subtitles.items():
                        first_episode.subtitles.setdefault(locale, subtitle)
                    subtitle_map = _locale_map(first_episode.subtitles)
                    if not subs_all and all(loc.lower() in subtitle_map for loc in subs_langs):
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
            if locale.lower() not in {available.lower() for available in available_subtitles}
        ]
        print(
            "Tracks selected: "
            f"audio=[{', '.join(track_title(version.audio_locale) for version in versions) or 'none'}], "
            f"subtitles=[{', '.join(track_title(locale) for locale in subs_langs) or 'none'}]"
        )
        if missing_audio:
            print(f"Warning: Audio tracks unavailable: {', '.join(missing_audio)}")
        if missing_subtitles:
            print(f"Warning: Subtitle tracks unavailable: {', '.join(missing_subtitles)}")

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
                    f"{track_title(track.locale)}"
                    + (" (default)" if track.is_default else "")
                    for track in sub_tracks
                )
            )
        elif subs_langs:
            print("Downloaded subtitles: none")

        video_file: Optional[str] = None
        audio_tracks: List[MediaTrack] = []
        video_download_args = None

        # Prepare track metadata
        audio_descriptors = []
        for i, version in enumerate(versions):
            content_id = version.guid or base_content_id
            ep = playback_cache.get(content_id)
            if ep is None:
                ep = get_episode(
                    client,
                    content_id,
                    debug=debug,
                    playback_id=content_id,
                )
                playback_cache[content_id] = ep
                active_streams[content_id] = ep.token

            prepared = _prepare_media_track(
                client, ep, content_id, audio_quality, video_quality, debug
            )

            if i == 0:
                video_download_args = (
                    prepared["video_base_url"],
                    prepared["video_rep_id"],
                    prepared["video_set"],
                    prepared["video_keys"],
                    prepared["period_duration_seconds"],
                    content_id,
                )

            print(f"Downloading {track_title(version.audio_locale)} audio...")
            try:
                audio_file = download_parts(
                    prepared["audio_base_url"],
                    prepared["audio_rep_id"],
                    prepared["audio_set"],
                    prepared["audio_keys"],
                    ep_title=info.title,
                    progress_cb=progress_cb,
                    pool=shared_pool,
                    track_type="audio",
                    period_duration_seconds=prepared["period_duration_seconds"],
                )
            except Exception as exc:
                if not _stream_expired_error(exc):
                    raise
                print(
                    f"\nPlayback stream expired for {track_title(version.audio_locale)}; "
                    "refreshing MPD and retrying track...",
                    flush=True,
                )
                refreshed_ep = get_episode(
                    client,
                    content_id,
                    debug=debug,
                    playback_id=version.guid or content_id,
                )
                previous_token = active_streams.get(content_id)
                if previous_token and previous_token != refreshed_ep.token:
                    delete_stream(client, content_id, previous_token)
                ep = refreshed_ep
                playback_cache[content_id] = ep
                active_streams[content_id] = ep.token
                prepared = _prepare_media_track(
                    client, ep, content_id, audio_quality, video_quality, debug
                )
                audio_file = download_parts(
                    prepared["audio_base_url"],
                    prepared["audio_rep_id"],
                    prepared["audio_set"],
                    prepared["audio_keys"],
                    ep_title=info.title,
                    progress_cb=progress_cb,
                    pool=shared_pool,
                    track_type="audio",
                    period_duration_seconds=prepared["period_duration_seconds"],
                )
            audio_tracks.append(
                MediaTrack(
                    file=audio_file,
                    locale=version.audio_locale,
                    is_default=len(audio_tracks) == 0,
                )
            )
            print(
                f"Downloaded audio: {track_title(version.audio_locale)}"
                + (" (default)" if audio_tracks[-1].is_default else "")
            )

        # Download video only after every requested audio track has completed.
        # All playback sessions remain active until the final cleanup block,
        # because manifests and licenses for later tracks may still depend on
        # their respective tokens.
        if video_download_args is not None:
            (
                video_base_url,
                video_rep_id,
                video_set,
                video_keys,
                period_duration_seconds,
                video_content_id,
            ) = video_download_args
            print("Downloading video...")
            try:
                video_file = download_parts(
                    video_base_url,
                    video_rep_id,
                    video_set,
                    video_keys,
                    ep_title=info.title,
                    progress_cb=progress_cb,
                    pool=shared_pool,
                    track_type="video",
                    period_duration_seconds=period_duration_seconds,
                )
            except Exception as exc:
                if not _stream_expired_error(exc):
                    raise
                print(
                    "\nPlayback stream expired for video; refreshing MPD and retrying track...",
                    flush=True,
                )
                refreshed_ep = get_episode(
                    client,
                    video_content_id,
                    debug=debug,
                    playback_id=video_content_id,
                )
                previous_token = active_streams.get(video_content_id)
                if previous_token and previous_token != refreshed_ep.token:
                    delete_stream(client, video_content_id, previous_token)
                playback_cache[video_content_id] = refreshed_ep
                active_streams[video_content_id] = refreshed_ep.token
                prepared = _prepare_media_track(
                    client,
                    refreshed_ep,
                    video_content_id,
                    audio_quality,
                    video_quality,
                    debug,
                )
                video_file = download_parts(
                    prepared["video_base_url"],
                    prepared["video_rep_id"],
                    prepared["video_set"],
                    prepared["video_keys"],
                    ep_title=info.title,
                    progress_cb=progress_cb,
                    pool=shared_pool,
                    track_type="video",
                    period_duration_seconds=prepared["period_duration_seconds"],
                )

        if not video_file:
            raise RuntimeError("No video file downloaded!")

        _invoke_progress_cb(
            progress_cb,
            info.title,
            1,
            1,
            "",
            0.0,
            "muxing",
        )

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
                raise RuntimeError(f"Output MKV failed stream integrity verification: {msg}")
        except FileNotFoundError:
            pass

        atomic_finalize(temp_output_filename, output_filename)
        print(
            "\nTracks in output: "
            f"audio=[{', '.join(track_title(track.locale) + (' (default)' if track.is_default else '') for track in audio_tracks)}], "
            f"subtitles=[{', '.join(track_title(track.locale) + (' (default)' if track.is_default else '') for track in sub_tracks) or 'none'}]"
        )
        print(f"Download finished! Output file: {output_filename}\n")
        return output_filename

    finally:
        shared_pool.close()
        print("Cleaning up...")
        for content_id, token in active_streams.items():
            if content_id and token:
                delete_stream(client, content_id, token)


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
) -> None:
    """download an entire season"""
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
) -> None:
    """grab everything for a series"""
    # Catalog endpoints require concrete locales. Sending ``all`` here makes
    # Crunchyroll return only its preferred/default version, which prevents
    # the later playback requests from discovering every dub.
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
            # The season endpoint may expose only the preferred audio version.
            # The episode object contains the complete dub-version list.
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
        )
        print()
