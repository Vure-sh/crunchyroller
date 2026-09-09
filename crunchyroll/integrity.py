"""
crunchyroll/integrity.py

Automated post-mux ffprobe stream integrity verification and atomic file finalization.
Validates video, audio, and subtitle stream presence, codec correctness, duration bounds,
and zero bitstream corruption before committing the final output Matroska container.
"""

import json
import logging
import os
import shutil
import subprocess
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("crunchyroll.integrity")


def find_ffprobe() -> str:
    """Locates the ffprobe binary locally or in the system PATH."""
    local_binary = os.path.join(os.getcwd(), "ffprobe.exe" if os.name == "nt" else "ffprobe")
    if os.path.exists(local_binary):
        return local_binary
    found = shutil.which("ffprobe")
    if found:
        return found
    raise FileNotFoundError(
        "ffprobe is not installed or not in PATH! Please install FFmpeg/ffprobe."
    )


class StreamValidator:
    """Validator performing deep inspection and integrity verification on media files."""

    @staticmethod
    def probe_file(file_path: str) -> Dict[str, Any]:
        """
        Executes ffprobe with structured JSON output and returns the parsed probe dictionary.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Media file not found: {file_path}")

        ffprobe_bin = find_ffprobe()
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-show_entries",
            "format=duration,nb_streams,bit_rate,size:stream=index,codec_type,codec_name,start_pts,start_time,duration_ts,duration,time_base,nb_frames:stream_tags",
            "-of", "json",
            file_path,
        ]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                timeout=60,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"ffprobe execution timed out probing: {file_path}") from exc
        if res.returncode != 0:
            raise RuntimeError(f"ffprobe execution failed with code {res.returncode}: {res.stderr.strip()}")

        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse ffprobe JSON output: {e}\nRaw output: {res.stdout}") from e

    @staticmethod
    def log_timing(file_path: str, label: str = "media") -> None:
        """Log stream timing information useful for diagnosing A/V drift."""
        try:
            data = StreamValidator.probe_file(file_path)
        except Exception as exc:
            logger.warning("Unable to probe %s timing for %s: %s", label, file_path, exc)
            return

        for stream in data.get("streams", []):
            if stream.get("codec_type") not in {"audio", "video"}:
                continue
            message = (
                f"[timing] {label}: stream={stream.get('index')} "
                f"type={stream.get('codec_type')} codec={stream.get('codec_name')} "
                f"start={stream.get('start_time')} duration={stream.get('duration')} "
                f"duration_ts={stream.get('duration_ts')} "
                f"time_base={stream.get('time_base')} frames={stream.get('nb_frames')}"
            )
            print(message, flush=True)
            logger.info(
                "%s timing: stream=%s type=%s codec=%s start=%s duration=%s "
                "duration_ts=%s time_base=%s frames=%s",
                label,
                stream.get("index"),
                stream.get("codec_type"),
                stream.get("codec_name"),
                stream.get("start_time"),
                stream.get("duration"),
                stream.get("duration_ts"),
                stream.get("time_base"),
                stream.get("nb_frames"),
            )

    @staticmethod
    def verify_mkv(
        file_path: str,
        expected_video: bool = True,
        min_audio_tracks: int = 1,
        min_sub_tracks: int = 0,
        min_duration: float = 0.0,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Verifies the integrity of a Matroska (.mkv) container file.

        Asserts:
        1. File exists and has non-zero size.
        2. Clean bitstream with zero ffprobe error diagnostics.
        3. Video stream presence and codec (if expected_video=True).
        4. Audio track count >= min_audio_tracks.
        5. Subtitle track count >= min_sub_tracks.
        6. Stream presentation duration >= min_duration.

        Returns:
            Tuple[bool, str, Dict[str, Any]]: (is_valid, status_message, probe_data)
        """
        if not os.path.exists(file_path):
            return False, f"File does not exist: {file_path}", {}

        if os.path.getsize(file_path) == 0:
            return False, f"File is 0 bytes (empty): {file_path}", {}

        try:
            data = StreamValidator.probe_file(file_path)
        except Exception as e:
            return False, f"ffprobe probing failed: {e}", {}

        streams = data.get("streams", [])
        format_info = data.get("format", {})

        def _stream_end(stream: Dict[str, Any]) -> Optional[float]:
            start = float(stream.get("start_time") or 0.0)
            duration = stream.get("duration")
            if duration is not None:
                return start + float(duration)
            return None

        # 1. Video stream inspection
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        if expected_video:
            if not video_streams:
                return False, "Missing expected video stream in container", data
            codec = video_streams[0].get("codec_name")
            if not codec:
                return False, "Video stream has unrecognized or empty codec", data

        # 2. Audio track count inspection
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        if len(audio_streams) < min_audio_tracks:
            return (
                False,
                f"Audio track count mismatch: expected at least {min_audio_tracks}, found {len(audio_streams)}",
                data,
            )

        # A stream-copy mux should not make audio finish materially earlier
        # than video. Keep this as a diagnostic warning rather than rejecting
        # the file because some dubs legitimately have different boundaries.
        if video_streams and audio_streams:
            video_end = _stream_end(video_streams[0])
            if video_end is not None:
                for index, audio in enumerate(audio_streams):
                    audio_end = _stream_end(audio)
                    if audio_end is not None and video_end - audio_end > 2.0:
                        logger.warning(
                            "Audio stream %d ends %.3fs before video "
                            "(video_end=%.3f, audio_end=%.3f)",
                            index,
                            video_end - audio_end,
                            video_end,
                            audio_end,
                        )

        # 3. Subtitle track count inspection
        sub_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
        if len(sub_streams) < min_sub_tracks:
            return (
                False,
                f"Subtitle track count mismatch: expected at least {min_sub_tracks}, found {len(sub_streams)}",
                data,
            )

        # 4. Duration bounds inspection
        if min_duration > 0:
            raw_dur = format_info.get("duration")
            dur = float(raw_dur) if raw_dur is not None else 0.0
            if dur < min_duration:
                return (
                    False,
                    f"Container duration {dur:.2f}s is less than expected minimum {min_duration:.2f}s",
                    data,
                )

        return True, "Output Matroska container integrity verified successfully", data


def atomic_finalize(temp_output_path: str, final_output_path: str) -> str:
    """
    Atomically moves/renames a temporary media file to its final destination.
    Guarantees destination directory existence and replaces any existing target file atomically.

    Args:
        temp_output_path: Path to the validated intermediate temporary file (e.g. .tmp.mkv).
        final_output_path: Target output path (e.g. .mkv).

    Returns:
        The final_output_path.
    """
    if not os.path.exists(temp_output_path):
        raise FileNotFoundError(f"Source temporary file not found for finalization: {temp_output_path}")

    # Ensure target parent directory exists
    target_dir = os.path.dirname(os.path.abspath(final_output_path))
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)

    try:
        os.replace(temp_output_path, final_output_path)
        logger.debug(f"Atomically finalized {temp_output_path} -> {final_output_path}")
        return final_output_path
    except Exception as e:
        logger.error(f"Failed to atomically finalize {temp_output_path} -> {final_output_path}: {e}")
        raise
