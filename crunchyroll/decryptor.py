"""Backward-compatible decryptor shim.

The original Python AES-CTR CENC decryption has been replaced by mp4decrypt
(from Bento4), which is invoked by N_m3u8DL-RE during the download phase.

This module is kept for backward compatibility (e.g. older tests or external
callers that import decrypt_mp4 or decrypt_stream directly).  It delegates
to the new tools.decrypt_with_mp4decrypt() helper.

_decrypt_with_ffmpeg is retained as a no-op stub so that any tests that import
it do not crash with an ImportError.
"""

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Dict, Optional, Union

from .tools import decrypt_with_mp4decrypt

logger = logging.getLogger("crunchyroll.decryptor")


def _decrypt_with_ffmpeg(input_file: str, key_hex: str, output_file: str) -> bool:
    """Legacy FFmpeg-based decryption stub (no longer used in the main pipeline).

    Kept for backward compatibility with tests that import this symbol directly.
    Calls FFmpeg with -decryption_key to attempt AES-CTR decryption.

    Returns:
        True if FFmpeg succeeded, False otherwise.
    """
    from .merger import find_ffmpeg
    try:
        ffmpeg = find_ffmpeg()
    except FileNotFoundError:
        return False

    cmd = [
        ffmpeg, "-y",
        "-decryption_key", key_hex,
        "-i", input_file,
        "-c", "copy",
        "-copyts",
        output_file,
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def decrypt_stream(
    input_file: str,
    keys: Optional[Dict[bytes, bytes]],
    output_file: str,
    fallback_only: bool = False,
) -> str:
    """Decrypt an encrypted MP4 stream using mp4decrypt.

    Args:
        input_file: Path to source raw fragmented MP4 file.
        keys: Mapping of KID -> Decryption Key bytes.
        output_file: Path to write clean decrypted MP4 stream.
        fallback_only: Ignored (kept for API compatibility).

    Returns:
        The output_file path.
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # If no keys, stream-copy directly
    if not keys:
        shutil.copy2(input_file, output_file)
        return output_file

    return decrypt_with_mp4decrypt(input_file, keys, output_file)


def decrypt_mp4(
    parts: Union[str, bytes],
    keys: Optional[Dict[bytes, bytes]],
    output_filename: str,
) -> str:
    """Backward-compatible wrapper supporting both file paths and byte buffers.

    Args:
        parts: Either a file path (str) or raw encrypted bytes.
        keys: Mapping of KID -> Key bytes.
        output_filename: Destination path.

    Returns:
        The output_filename path.
    """
    if isinstance(parts, str):
        return decrypt_stream(parts, keys, output_filename)

    # In-memory bytes input: write to temporary file then decrypt
    with tempfile.NamedTemporaryFile(suffix=".raw.mp4", delete=False) as tf:
        tmp_raw = tf.name
        tf.write(parts)

    try:
        return decrypt_stream(tmp_raw, keys, output_filename)
    finally:
        if os.path.exists(tmp_raw):
            try:
                os.remove(tmp_raw)
            except OSError:
                pass
