"""Binary discovery and subprocess wrappers for N_m3u8DL-RE and mp4decrypt."""

import os
import shutil
import subprocess
import sys
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("crunchyroll.tools")


def _project_root() -> str:
    """Return the absolute path of the project root directory."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _find_binary(names: List[str]) -> str:
    """Search for a binary in: project root/bin, exe dir/bin, PATH."""
    root = _project_root()
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    search_dirs = [
        os.path.join(exe_dir, "bin"),
        os.path.join(root, "bin"),
        os.path.join(os.getcwd(), "bin"),
        exe_dir,
        root,
        os.getcwd(),
        os.path.join(exe_dir, "_internal"),
        os.path.join(exe_dir, "_internal", "bin"),
    ]
    if hasattr(sys, "_MEIPASS"):
        search_dirs.append(sys._MEIPASS)
        search_dirs.append(os.path.join(sys._MEIPASS, "bin"))

    for name in names:
        for d in search_dirs:
            candidate = os.path.join(d, name)
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
        found = shutil.which(name)
        if found:
            return found

    raise FileNotFoundError(
        f"Could not find any of {names}.\n"
        "Place the binary in the 'bin/' folder next to crunchyroller.exe or in the project folder."
    )


def find_n_m3u8dl_re() -> str:
    """Locate the N_m3u8DL-RE executable."""
    return _find_binary(["N_m3u8DL-RE.exe", "N_m3u8DL-RE"])


def find_mp4decrypt() -> str:
    """Locate the mp4decrypt executable (Bento4)."""
    return _find_binary(["mp4decrypt.exe", "mp4decrypt"])


def format_keys_for_n_m3u8dl(keys: Dict[bytes, bytes]) -> List[str]:
    """Format Widevine KID->Key pairs as --key KID_HEX:KEY_HEX arguments."""
    args: List[str] = []
    for kid, key in keys.items():
        args += ["--key", f"{kid.hex()}:{key.hex()}"]
    return args


def run_n_m3u8dl_re(
    mpd_url: str,
    keys: Dict[bytes, bytes],
    output_dir: str,
    base_name: str,
    bearer_token: str,
    video_quality: Optional[str] = None,
    audio_only: bool = False,
    extra_args: Optional[List[str]] = None,
    mp4decrypt_path: Optional[str] = None,
    audio_quality: Optional[str] = None,
) -> Dict[str, object]:
    """Download and decrypt a DASH stream using N_m3u8DL-RE.

    N_m3u8DL-RE handles:
      1. MPD parsing and segment downloading (selected video + all audio tracks)
      2. CENC decryption via the embedded mp4decrypt call (--key + --decryption-binary-path)
      3. Writes decrypted per-track files ready for FFmpeg muxing

    Returns dict with keys:
      "video"       -> str  path to the decrypted video MP4
      "audio_files" -> list paths to decrypted audio MP4 files (one per dub track)
    """
    binary = find_n_m3u8dl_re()
    mp4d = mp4decrypt_path or find_mp4decrypt()

    os.makedirs(output_dir, exist_ok=True)
    tmp_dir = os.path.join(output_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    cmd: List[str] = [
        binary,
        mpd_url,
        "--save-dir", output_dir,
        "--save-name", base_name,
        "--tmp-dir", tmp_dir,
        # Let N_m3u8DL-RE call mp4decrypt internally
        "--decryption-binary-path", mp4d,
        # Auth headers for Crunchyroll CDN
        "--header", f"Authorization: Bearer {bearer_token}",
        "--header", "Origin: https://static.crunchyroll.com",
        "--header", "Referer: https://static.crunchyroll.com/",
        # Do NOT auto-mux; FFmpeg will handle that (omitting --mux-after-done disables it)
        # Keep correct timestamps
        "--no-date-info",
        # Log level
        "--log-level", "INFO",
    ]

    # Decryption keys (KID:KEY hex pairs)
    cmd += format_keys_for_n_m3u8dl(keys)

    # Video quality / audio-only selection
    if audio_only:
        # Audio-only download (dub streams): drop video entirely
        cmd += ["--drop-video", ".*"]
    else:
        v_digits = "".join(filter(str.isdigit, video_quality or ""))
        if v_digits and (video_quality or "").lower() not in ("best", "auto", "max"):
            cmd += ["--select-video", f'res=".*{v_digits}.*":for=best']
        else:
            cmd += ["--select-video", "for=best"]

    # Audio quality selection (avoid downloading redundant 192k/128k/96k streams for same lang)
    a_digits = "".join(filter(str.isdigit, audio_quality or ""))
    if a_digits and (audio_quality or "").lower() not in ("best", "auto", "max"):
        cmd += ["--select-audio", f'id=".*{a_digits}k.*":for=best']
    else:
        cmd += ["--select-audio", "for=best"]

    # No subtitles here — existing code fetches .ass from the API
    cmd += ["--drop-subtitle", ".*"]

    if extra_args:
        cmd += extra_args

    logger.info("[n_m3u8dl-re] Command: %s", " ".join(cmd))
    print(f"[n_m3u8dl-re] Downloading: {base_name}", flush=True)

    result = subprocess.run(cmd, cwd=output_dir)

    # If it failed and we had specific quality filters, retry with best available fallback
    if result.returncode != 0 and (video_quality or audio_quality):
        logger.warning("[n_m3u8dl-re] Specific quality selection failed; retrying with best available stream...")
        fallback_cmd = list(cmd)
        for idx, arg in enumerate(fallback_cmd):
            if arg == "--select-video" and idx + 1 < len(fallback_cmd):
                fallback_cmd[idx + 1] = "for=best"
            elif arg == "--select-audio" and idx + 1 < len(fallback_cmd):
                fallback_cmd[idx + 1] = "for=best"
        result = subprocess.run(fallback_cmd, cwd=output_dir)

    if result.returncode != 0:
        raise RuntimeError(
            f"N_m3u8DL-RE exited with code {result.returncode} for '{base_name}'.\n"
            "Check the output above for details."
        )

    # Discover output files written by N_m3u8DL-RE.
    # Audio tracks may be .m4a (newer N_m3u8DL-RE) or .mp4 (older).
    AUDIO_EXTS = (".mp4", ".m4a")
    video_file: Optional[str] = None
    audio_files: List[str] = []

    for fname in sorted(os.listdir(output_dir)):
        if not fname.startswith(base_name):
            continue
        full = os.path.join(output_dir, fname)
        if not os.path.isfile(full):
            continue
        lower = fname.lower()
        # Dedicated audio file: contains a language tag (.ja-JP., .en-US., etc.)
        # OR has a known audio-only extension (.m4a)
        if lower.endswith(".m4a"):
            audio_files.append(full)
        elif lower.endswith(".mp4"):
            if "_audio" in lower:
                audio_files.append(full)
            elif video_file is None:
                video_file = full

    if video_file is None:
        # Fallback: largest .mp4 is video
        mp4s = [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.startswith(base_name) and f.lower().endswith(".mp4")
            and os.path.isfile(os.path.join(output_dir, f))
        ]
        if mp4s:
            video_file = max(mp4s, key=os.path.getsize)
            audio_files = [f for f in mp4s if f != video_file]

    if not video_file and not audio_only:
        raise RuntimeError(
            f"N_m3u8DL-RE completed but no output .mp4 found in '{output_dir}'.\n"
            f"Files: {os.listdir(output_dir)}"
        )

    return {
        "video": video_file,
        "audio_files": audio_files,
    }


def decrypt_with_mp4decrypt(
    encrypted_file: str,
    keys: Dict[bytes, bytes],
    output_file: str,
    mp4decrypt_path: Optional[str] = None,
) -> str:
    """Decrypt a single CENC-encrypted MP4 using mp4decrypt (standalone use).

    Args:
        encrypted_file: Path to the encrypted fMP4/MP4.
        keys: Widevine KID -> Key mapping.
        output_file: Destination path.
        mp4decrypt_path: Explicit path; auto-detected if None.

    Returns:
        The output_file path.
    """
    mp4d = mp4decrypt_path or find_mp4decrypt()
    cmd: List[str] = [mp4d]
    for kid, key in keys.items():
        cmd += ["--key", f"{kid.hex()}:{key.hex()}"]
    cmd += [encrypted_file, output_file]

    logger.info("[mp4decrypt] %s", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"mp4decrypt failed (exit {r.returncode}):\n"
            f"stdout: {r.stdout.strip()}\n"
            f"stderr: {r.stderr.strip()}"
        )
    return output_file
