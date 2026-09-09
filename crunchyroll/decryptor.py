"""
crunchyroll/decryptor.py

High-performance CENC AES-128-CTR decryption and stream decoupling.
Dual-mode decryption architecture:
1. Primary: Ultra-fast native FFmpeg CENC demuxer (-decryption_key <hex>).
2. Fallback: Strictly memory-bounded (< 100 MB peak RAM) streaming ISO-BMFF box parser
   and chunk-by-chunk AES-128-CTR decryptor utilizing small fixed 4 MB buffers.
"""

import logging
import os
import shutil
import struct
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple, Union

from Crypto.Cipher import AES
from Crypto.Util import Counter

from .merger import find_ffmpeg

logger = logging.getLogger("crunchyroll.decryptor")

BUFFER_SIZE = 4 * 1024 * 1024  # 4 MB fixed streaming chunk size


def _read_u32(buf: Union[bytes, bytearray], pos: int) -> int:
    if pos + 4 > len(buf):
        return 0
    return struct.unpack(">I", buf[pos : pos + 4])[0]


def _read_u16(buf: Union[bytes, bytearray], pos: int) -> int:
    if pos + 2 > len(buf):
        return 0
    return struct.unpack(">H", buf[pos : pos + 2])[0]


def _write_u32(buf: bytearray, pos: int, val: int) -> None:
    buf[pos : pos + 4] = struct.pack(">I", val)


def _copy_stream_chunks(src_f, dst_f, num_bytes: int, chunk_size: int = BUFFER_SIZE) -> None:
    """Stream copy a fixed number of bytes between file objects using bounded chunks."""
    remaining = num_bytes
    while remaining > 0:
        to_read = min(remaining, chunk_size)
        chunk = src_f.read(to_read)
        if not chunk:
            break
        dst_f.write(chunk)
        remaining -= len(chunk)


def _decrypt_with_ffmpeg(input_file: str, key_hex: str, output_file: str) -> bool:
    """Attempt high-speed native CENC decryption via FFmpeg."""
    try:
        ffmpeg_bin = find_ffmpeg()
    except Exception as e:
        logger.debug(f"FFmpeg binary not found for native decryption: {e}")
        return False

    cmd = [
        ffmpeg_bin,
        "-y",
        "-decryption_key",
        key_hex,
        "-copyts",
        "-i",
        input_file,
        "-c",
        "copy",
        output_file,
    ]

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=300,
        )
        if res.returncode == 0 and os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            return True
        logger.debug(f"FFmpeg native decryption failed (code {res.returncode}): {res.stderr}")
        if os.path.exists(output_file):
            try:
                os.remove(output_file)
            except OSError:
                pass
        return False
    except Exception as e:
        logger.debug(f"Exception during FFmpeg native decryption: {e}")
        if os.path.exists(output_file):
            try:
                os.remove(output_file)
            except OSError:
                pass
        return False


def _modify_moov_box(moov_bytes: bytearray) -> bytearray:
    """Rewrite sample descriptions in moov box from encrypted (encv/enca) to clean (avc1/mp4a)."""
    buf = bytearray(moov_bytes)
    for enc_tag, clean_tag in ((b"encv", b"avc1"), (b"enca", b"mp4a")):
        idx_enc = 0
        while True:
            idx_enc = buf.find(enc_tag, idx_enc)
            if idx_enc == -1:
                break

            buf[idx_enc : idx_enc + 4] = clean_tag
            enc_size_pos = idx_enc - 4
            enc_size = _read_u32(buf, enc_size_pos)
            idx_sinf = buf.find(b"sinf", idx_enc)
            if idx_sinf != -1 and idx_sinf < idx_enc + enc_size:
                sinf_start = idx_sinf - 4
                sinf_size = _read_u32(buf, sinf_start)
                if sinf_size > 0 and sinf_start + sinf_size <= len(buf):
                    del buf[sinf_start : sinf_start + sinf_size]
                    _write_u32(buf, enc_size_pos, max(0, enc_size - sinf_size))
                    for parent_tag in (b"stsd", b"stbl", b"minf", b"mdia", b"trak", b"moov"):
                        p_idx = 0
                        while True:
                            p_idx = buf.find(parent_tag, p_idx)
                            if p_idx == -1 or p_idx >= sinf_start:
                                break
                            p_size = _read_u32(buf, p_idx - 4)
                            _write_u32(buf, p_idx - 4, max(0, p_size - sinf_size))
                            p_idx += 4
            idx_enc += 4
    return buf


def _parse_moof_box(moof_bytes: bytes) -> Tuple[List[bytes], List[List[Tuple[int, int]]], List[int], Optional[int]]:
    """Parse moof fragment header to extract sample IVs, subsample maps, sample sizes, and data offset."""
    buf = moof_bytes
    buf_len = len(buf)
    sample_ivs: List[bytes] = []
    subsamples_list: List[List[Tuple[int, int]]] = []
    sample_sizes: List[int] = []
    default_sample_size = 0
    trun_data_offset: Optional[int] = None
    subsample_flag = False

    cur = 8  # skip moof header
    while cur + 8 <= buf_len:
        b_size = _read_u32(buf, cur)
        if b_size <= 0 or cur + b_size > buf_len:
            break
        b_type = bytes(buf[cur + 4 : cur + 8])

        if b_type == b"traf":
            t_cur = cur + 8
            t_end = min(cur + b_size, buf_len)
            while t_cur + 8 <= t_end:
                tb_size = _read_u32(buf, t_cur)
                if tb_size <= 0 or t_cur + tb_size > t_end:
                    break
                tb_type = bytes(buf[t_cur + 4 : t_cur + 8])

                if tb_type == b"tfhd":
                    tf_flags = (buf[t_cur + 9] << 16) | (buf[t_cur + 10] << 8) | buf[t_cur + 11]
                    p_tf = t_cur + 16
                    if tf_flags & 0x000001:
                        p_tf += 8  # base_data_offset
                    if tf_flags & 0x000002:
                        p_tf += 4  # sample_description_index
                    if tf_flags & 0x000008:
                        p_tf += 4  # default_sample_duration
                    if tf_flags & 0x000010 and p_tf + 4 <= t_end:
                        default_sample_size = _read_u32(buf, p_tf)

                elif tb_type == b"trun":
                    tr_flags = (buf[t_cur + 9] << 16) | (buf[t_cur + 10] << 8) | buf[t_cur + 11]
                    tr_count = _read_u32(buf, t_cur + 12)
                    p_tr = t_cur + 16
                    if tr_flags & 0x000001:
                        trun_data_offset = struct.unpack(">i", buf[p_tr : p_tr + 4])[0]
                        p_tr += 4
                    if tr_flags & 0x000004:
                        p_tr += 4  # first_sample_flags
                    for _ in range(tr_count):
                        if p_tr > t_end:
                            break
                        if tr_flags & 0x000100:
                            p_tr += 4  # sample_duration
                        s_size = _read_u32(buf, p_tr) if (tr_flags & 0x000200) else default_sample_size
                        if tr_flags & 0x000200:
                            p_tr += 4  # sample_size
                        if tr_flags & 0x000400:
                            p_tr += 4  # sample_flags
                        if tr_flags & 0x000800:
                            p_tr += 4  # sample_composition_time_offset
                        sample_sizes.append(s_size)

                elif tb_type in (b"senc", b"uuid"):
                    senc_flags = (buf[t_cur + 9] << 16) | (buf[t_cur + 10] << 8) | buf[t_cur + 11]
                    subsample_flag = bool(senc_flags & 0x000002)
                    senc_count = _read_u32(buf, t_cur + 12)
                    p_senc = t_cur + 16
                    for _ in range(senc_count):
                        if p_senc + 8 > t_end:
                            break
                        iv = bytes(buf[p_senc : p_senc + 8])
                        p_senc += 8
                        sample_ivs.append(iv)
                        subs: List[Tuple[int, int]] = []
                        if subsample_flag:
                            if p_senc + 2 > t_end:
                                break
                            sub_count = _read_u16(buf, p_senc)
                            p_senc += 2
                            for _ in range(sub_count):
                                if p_senc + 6 > t_end:
                                    break
                                c_len = _read_u16(buf, p_senc)
                                e_len = _read_u32(buf, p_senc + 2)
                                p_senc += 6
                                subs.append((c_len, e_len))
                        subsamples_list.append(subs)

                t_cur += tb_size
            break
        cur += b_size

    return sample_ivs, subsamples_list, sample_sizes, trun_data_offset


def decrypt_cenc_streaming(
    input_file: str,
    key: bytes,
    output_file: str,
    chunk_size: int = BUFFER_SIZE,
) -> None:
    """
    Streaming fallback decryption for fragmented MP4 (fMP4) CENC AES-128-CTR.
    Processes boxes sequentially without ever loading multi-gigabyte media into RAM.
    Strictly bounds memory usage (< 100 MB peak RSS, typically < 15 MB).
    """
    file_size = os.path.getsize(input_file)
    pending_ivs: List[bytes] = []
    pending_subs: List[List[Tuple[int, int]]] = []
    pending_sizes: List[int] = []
    pending_offset: Optional[int] = None

    with open(input_file, "rb") as src_f, open(output_file, "wb") as dst_f:
        while True:
            header = src_f.read(8)
            if not header or len(header) < 8:
                break

            box_size = struct.unpack(">I", header[0:4])[0]
            box_type = header[4:8]
            hdr_size = 8

            if box_size == 1:
                ext_hdr = src_f.read(8)
                if len(ext_hdr) < 8:
                    break
                box_size = struct.unpack(">Q", ext_hdr)[0]
                hdr_size = 16
                header = header + ext_hdr
            elif box_size == 0:
                box_size = file_size - (src_f.tell() - hdr_size)

            payload_size = box_size - hdr_size

            if box_type == b"moov":
                # moov contains metadata (usually < 2 MB), read and transform
                moov_raw = header + src_f.read(payload_size)
                modified_moov = _modify_moov_box(bytearray(moov_raw))
                dst_f.write(modified_moov)

            elif box_type == b"moof":
                # moof contains fragment headers (usually < 64 KB)
                moof_raw = header + src_f.read(payload_size)
                p_ivs, p_subs, p_sizes, p_off = _parse_moof_box(moof_raw)
                pending_ivs = p_ivs
                pending_subs = p_subs
                pending_sizes = p_sizes
                pending_offset = p_off
                dst_f.write(moof_raw)

            elif box_type == b"mdat":
                # Write mdat box header
                dst_f.write(header)

                if pending_ivs and key:
                    total_written = 0
                    for idx, iv in enumerate(pending_ivs):
                        iv_full = iv + b"\x00" * (16 - len(iv))
                        ctr = Counter.new(128, initial_value=int.from_bytes(iv_full, "big"))
                        cipher = AES.new(key, AES.MODE_CTR, counter=ctr)

                        subs = pending_subs[idx] if idx < len(pending_subs) else []
                        s_size = pending_sizes[idx] if idx < len(pending_sizes) else 0

                        if subs:
                            for clear_len, enc_len in subs:
                                if clear_len > 0:
                                    _copy_stream_chunks(src_f, dst_f, clear_len, chunk_size)
                                    total_written += clear_len
                                if enc_len > 0:
                                    rem_enc = enc_len
                                    while rem_enc > 0:
                                        cur_read = min(rem_enc, chunk_size)
                                        enc_chunk = src_f.read(cur_read)
                                        if not enc_chunk:
                                            break
                                        dec_chunk = cipher.decrypt(enc_chunk)
                                        dst_f.write(dec_chunk)
                                        rem_enc -= len(enc_chunk)
                                        total_written += len(enc_chunk)
                        else:
                            if s_size > 0:
                                rem_s = s_size
                                while rem_s > 0:
                                    cur_read = min(rem_s, chunk_size)
                                    enc_chunk = src_f.read(cur_read)
                                    if not enc_chunk:
                                        break
                                    dec_chunk = cipher.decrypt(enc_chunk)
                                    dst_f.write(dec_chunk)
                                    rem_s -= len(enc_chunk)
                                    total_written += len(enc_chunk)

                    # Copy any remaining unmapped mdat bytes
                    remaining_mdat = payload_size - total_written
                    if remaining_mdat > 0:
                        _copy_stream_chunks(src_f, dst_f, remaining_mdat, chunk_size)

                    pending_ivs = []
                    pending_subs = []
                    pending_sizes = []
                    pending_offset = None
                else:
                    # Clear mdat or no keys -> stream copy
                    _copy_stream_chunks(src_f, dst_f, payload_size, chunk_size)

            else:
                # ftyp, styp, sidx, etc. -> stream copy directly
                dst_f.write(header)
                _copy_stream_chunks(src_f, dst_f, payload_size, chunk_size)


def decrypt_stream(
    input_file: str,
    keys: Optional[Dict[bytes, bytes]],
    output_file: str,
    fallback_only: bool = False,
) -> str:
    """
    Decrypts an encrypted MP4 stream to the destination output file.
    Attempts high-speed native FFmpeg demuxer first, automatically falling back
    to memory-bounded streaming Python ISO-BMFF decryption if FFmpeg fails.

    Args:
        input_file: Path to source raw fragmented MP4 file.
        keys: Mapping of KID -> Decryption Key bytes.
        output_file: Path to write clean decrypted MP4 stream.
        fallback_only: If True, skips FFmpeg and executes streaming Python decryptor.

    Returns:
        The output_file path.
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # If no keys or clear stream, stream-copy directly
    if not keys:
        with open(input_file, "rb") as src_f, open(output_file, "wb") as dst_f:
            _copy_stream_chunks(src_f, dst_f, os.path.getsize(input_file))
        return output_file

    key_bytes = next(iter(keys.values()))
    key_hex = key_bytes.hex()

    if not fallback_only:
        success = _decrypt_with_ffmpeg(input_file, key_hex, output_file)
        if success:
            return output_file
        logger.info("FFmpeg native decryption unavailable or failed; using streaming Python fallback.")

    # Execute memory-bounded streaming Python fallback
    try:
        decrypt_cenc_streaming(input_file, key_bytes, output_file)
        return output_file
    except Exception as e:
        if os.path.exists(output_file):
            try:
                os.remove(output_file)
            except OSError:
                pass
        raise RuntimeError(f"Streaming CENC decryption failed: {e}") from e


def decrypt_mp4(
    parts: Union[str, bytes],
    keys: Optional[Dict[bytes, bytes]],
    output_filename: str,
) -> str:
    """
    Backward-compatible wrapper supporting both file paths and byte buffers.
    """
    if isinstance(parts, str):
        return decrypt_stream(parts, keys, output_filename)

    # In-memory bytes input: write to temporary raw stream and decrypt
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
