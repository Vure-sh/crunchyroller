"""Multi-track Matroska (MKV) multiplexer using FFmpeg."""

import logging
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from .types import EpisodeInfo, MediaTrack
from .utils import LANGUAGE_CODES, get_subprocess_kwargs, locale_base, track_title

logger = logging.getLogger("crunchyroll.merger")


def generate_ffmetadata(chapters: List[Dict[str, Any]]) -> str:
    """Generates standard FFMETADATA1 chapter definitions for FFmpeg."""
    lines = [";FFMETADATA1"]
    for ch in chapters:
        start_ms = int(round(float(ch["start"]) * 1000))
        end_ms = int(round(float(ch["end"]) * 1000))
        title = str(ch.get("name", "Chapter")).strip()
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={start_ms}")
        lines.append(f"END={end_ms}")
        lines.append(f"title={title}")
    return "\n".join(lines) + "\n"



def find_ffmpeg() -> str:
    """Locates ffmpeg binary locally or in the system PATH."""
    bin_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates = [
        os.path.join(os.getcwd(), bin_name),
        os.path.join(os.path.dirname(os.path.abspath(sys.executable)), bin_name),
        os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "_internal", bin_name),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", bin_name),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_internal", bin_name),
    ]
    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, bin_name))

    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)

    found = shutil.which("ffmpeg")
    if found:
        return found
    raise FileNotFoundError(
        "FFmpeg is not installed or not in PATH! Please install FFmpeg or place 'ffmpeg.exe' in the project folder."
    )


def merge_everything(
    video_file: Optional[str],
    audio_tracks: List[MediaTrack],
    sub_tracks: List[MediaTrack],
    output_file: str,
    info: EpisodeInfo,
    video_quality: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    chapters: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    Muxes video (optional), multi-audio dubs, and subtitle tracks into a single container (MKV/MKA).
    Inputs are fragmented MP4 streams whose timestamps are meaningful. Keep
    them intact while stream-copying; regenerating PTS globally can turn a
    small source offset into an audible/video sync error.
    """
    ffmpeg_bin = find_ffmpeg()

    args = [ffmpeg_bin, "-y"]

    has_video = bool(video_file and os.path.exists(video_file))

    # Video input (stream 0, if present)
    if has_video:
        args.extend(["-i", video_file])

    # Audio inputs
    for audio in audio_tracks:
        args.extend(["-i", audio.file])

    # Subtitle inputs
    for sub in sub_tracks:
        args.extend(["-i", sub.file])

    audio_offset = 1 if has_video else 0
    is_m4a = output_file.lower().endswith(".m4a")

    chapters_file = None
    chapters_input_idx = None
    if chapters:
        try:
            chapters_content = generate_ffmetadata(chapters)
            chapters_file = output_file + ".chapters.txt"
            with open(chapters_file, "w", encoding="utf-8") as f:
                f.write(chapters_content)
            chapters_input_idx = audio_offset + len(audio_tracks) + len(sub_tracks)
            args.extend(["-i", chapters_file])
        except Exception as exc:
            logger.warning("Failed to prepare chapters metadata: %s", exc)
            chapters_file = None
            chapters_input_idx = None

    # Map video track (if present)
    if has_video:
        args.extend(["-map", "0:v:0"])

    # Map audio tracks
    for i in range(len(audio_tracks)):
        args.extend(["-map", f"{audio_offset + i}:a:0"])

    # Map subtitle tracks (skip embedding into pure .m4a audio container)
    if not is_m4a:
        for j in range(len(sub_tracks)):
            args.extend(["-map", f"{audio_offset + len(audio_tracks) + j}"])

    # Map chapters
    if chapters_input_idx is not None:
        args.extend(["-map_chapters", str(chapters_input_idx)])

    # Codec copying
    if has_video:
        args.extend(["-c:v", "copy"])
    args.extend(["-c:a", "copy"])
    if sub_tracks and not is_m4a:
        args.extend(["-c:s", "copy"])

    # Video metadata (quality title and BPS / NUMBER_OF_BYTES tags for MediaInfo)
    if has_video:
        if video_quality:
            args.extend(["-metadata:s:v:0", f"title={video_quality}"])
        try:
            v_size = os.path.getsize(video_file)
            if v_size > 0:
                args.extend(["-metadata:s:v:0", f"NUMBER_OF_BYTES={v_size}"])
                if duration_seconds and duration_seconds > 0:
                    v_bps = int((v_size * 8) / duration_seconds)
                    args.extend(["-metadata:s:v:0", f"BPS={v_bps}"])
        except OSError:
            pass

    # Audio metadata (ISO 639-2/B language codes, localized titles with bitrate, and BPS tags)
    for i, audio in enumerate(audio_tracks):
        lang_code = LANGUAGE_CODES.get(audio.locale, audio.locale)
        base_title = track_title(audio.locale)

        a_bps = audio.bitrate
        a_size = None
        if os.path.exists(audio.file):
            try:
                a_size = os.path.getsize(audio.file)
                if a_size > 0 and (not a_bps or a_bps <= 0) and duration_seconds and duration_seconds > 0:
                    a_bps = int((a_size * 8) / duration_seconds)
            except OSError:
                pass

        if audio.title:
            title = audio.title
        elif a_bps and a_bps > 0:
            kbps = round(a_bps / 1000)
            title = f"{base_title} [{kbps} kbps]"
        else:
            title = base_title

        args.extend([
            f"-metadata:s:a:{i}", f"language={lang_code}",
            f"-metadata:s:a:{i}", f"title={title}",
        ])
        if a_bps and a_bps > 0:
            args.extend([f"-metadata:s:a:{i}", f"BPS={a_bps}"])
        if a_size and a_size > 0:
            args.extend([f"-metadata:s:a:{i}", f"NUMBER_OF_BYTES={a_size}"])

    # Subtitle metadata and dispositions (only when embedded into MKV/MKA)
    if not is_m4a:
        for j, sub in enumerate(sub_tracks):
            lang_code = LANGUAGE_CODES.get(locale_base(sub.locale), locale_base(sub.locale))
            base_title = track_title(locale_base(sub.locale))
            title = f"{base_title} (CC)" if sub.is_cc else track_title(sub.locale)
            args.extend([
                f"-metadata:s:s:{j}", f"language={lang_code}",
                f"-metadata:s:s:{j}", f"title={title}",
            ])

    # Track dispositions. Explicit defaults take precedence; retain the
    # historical first-track fallback for callers that do not set is_default.
    default_audio_index = next(
        (i for i, track in enumerate(audio_tracks) if track.is_default),
        0 if audio_tracks else -1,
    )
    for i in range(len(audio_tracks)):
        disposition = "default" if i == default_audio_index else "0"
        args.extend([f"-disposition:a:{i}", disposition])

    if not is_m4a:
        default_subtitle_index = next(
            (i for i, track in enumerate(sub_tracks) if track.is_default),
            0 if sub_tracks else -1,
        )
        for j, sub in enumerate(sub_tracks):
            parts = ["default"] if j == default_subtitle_index else ["0"]
            if sub.is_cc:
                parts = [p for p in parts if p != "0"]  # drop the "0" placeholder
                parts.append("hearing_impaired")
                if not parts:
                    parts = ["hearing_impaired"]
            disposition = "+".join(parts) if parts else "0"
            args.extend([f"-disposition:s:{j}", disposition])

    # Global metadata tags (fixed season_number and episode_number)
    meta_title = (
        f"S{info.episode_metadata.season_number:02d}E{info.episode_metadata.episode_number:02d} - {info.title}"
    )
    args.extend([
        "-metadata:g", f"title={meta_title}",
        "-metadata:g", f"show={info.episode_metadata.series_title}",
        "-metadata:g", f"track={info.episode_metadata.episode_number}",
        "-metadata:g", f"season_number={info.episode_metadata.season_number}",
        "-metadata:g", f"episode_number={info.episode_metadata.episode_number}",
    ])

    args.append(output_file)

    try:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=600,
                **get_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except OSError:
                    pass
            raise RuntimeError("ffmpeg timed out after 10 minutes while muxing") from exc
        if result.returncode != 0:
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except OSError:
                    pass
            raise RuntimeError(f"ffmpeg failed: {result.stderr}")
    finally:
        if chapters_file and os.path.exists(chapters_file):
            try:
                os.remove(chapters_file)
            except OSError:
                pass

    # Clean up intermediate temporary files
    if video_file and os.path.exists(video_file):
        try:
            os.remove(video_file)
        except OSError:
            pass

    for audio in audio_tracks:
        if os.path.exists(audio.file):
            try:
                os.remove(audio.file)
            except OSError:
                pass

    for sub in sub_tracks:
        if not is_m4a and os.path.exists(sub.file):
            try:
                os.remove(sub.file)
            except OSError:
                pass

    print(f"\nDownload finished! Output file: {output_file}\n")
