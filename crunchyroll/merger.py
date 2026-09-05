"""Multi-track Matroska (MKV) multiplexer using FFmpeg."""

import logging
import os
import shutil
import subprocess
import sys
from typing import List, Optional

from .types import EpisodeInfo, MediaTrack
from .utils import LANGUAGE_CODES, track_title

logger = logging.getLogger("crunchyroll.merger")


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
    video_file: str,
    audio_tracks: List[MediaTrack],
    sub_tracks: List[MediaTrack],
    output_file: str,
    info: EpisodeInfo,
) -> None:
    """
    Muxes video, multi-audio dubs, and subtitle tracks into a single MKV container.
    Inputs are fragmented MP4 streams whose timestamps are meaningful. Keep
    them intact while stream-copying; regenerating PTS globally can turn a
    small source offset into an audible/video sync error.
    """
    ffmpeg_bin = find_ffmpeg()

    args = [ffmpeg_bin, "-y"]

    # Video input (stream 0)
    args.extend(["-i", video_file])

    # Audio inputs (streams 1 .. N)
    for audio in audio_tracks:
        args.extend(["-i", audio.file])

    # Subtitle inputs (streams N+1 .. M)
    for sub in sub_tracks:
        args.extend(["-i", sub.file])

    # Map video track
    args.extend(["-map", "0:v:0"])

    # Map audio tracks
    for i in range(len(audio_tracks)):
        args.extend(["-map", f"{1 + i}:a:0"])

    # Map subtitle tracks
    for j in range(len(sub_tracks)):
        args.extend(["-map", f"{1 + len(audio_tracks) + j}"])

    # Codec copying
    args.extend(["-c:v", "copy", "-c:a", "copy"])
    if sub_tracks:
        args.extend(["-c:s", "copy"])

    # Audio metadata (ISO 639-2/B language codes and localized titles)
    for i, audio in enumerate(audio_tracks):
        lang_code = LANGUAGE_CODES.get(audio.locale, audio.locale)
        title = track_title(audio.locale)
        args.extend([
            f"-metadata:s:a:{i}", f"language={lang_code}",
            f"-metadata:s:a:{i}", f"title={title}",
        ])

    # Subtitle metadata
    for j, sub in enumerate(sub_tracks):
        lang_code = LANGUAGE_CODES.get(sub.locale, sub.locale)
        title = track_title(sub.locale)
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

    default_subtitle_index = next(
        (i for i, track in enumerate(sub_tracks) if track.is_default),
        0 if sub_tracks else -1,
    )
    for j in range(len(sub_tracks)):
        disposition = "default" if j == default_subtitle_index else "0"
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
        output_file,
    ])

    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        if os.path.exists(output_file):
            try:
                os.remove(output_file)
            except OSError:
                pass
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    # Clean up intermediate temporary files
    if os.path.exists(video_file):
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
        if os.path.exists(sub.file):
            try:
                os.remove(sub.file)
            except OSError:
                pass

    print(f"\nDownload finished! Output file: {output_file}\n")
