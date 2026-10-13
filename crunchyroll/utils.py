import os
import re
import subprocess
import sys
from typing import NamedTuple, Optional


def get_subprocess_kwargs() -> dict:
    """Return platform-specific kwargs for subprocess to prevent console window popup on Windows."""
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return kwargs


LANGUAGE_NAMES = {
    "ja-JP": "日本語",
    "en-US": "English",
    "en-IN": "English (India)",
    "id-ID": "Bahasa Indonesia",
    "ms-MY": "Bahasa Melayu",
    "ca-ES": "Català",
    "de-DE": "Deutsch",
    "es-419": "Español (América Latina)",
    "es-ES": "Español (España)",
    "fr-FR": "Français",
    "it-IT": "Italiano",
    "pl-PL": "Polski",
    "pt-BR": "Português (Brasil)",
    "pt-PT": "Português (Portugal)",
    "vi-VN": "Tiếng Việt",
    "tr-TR": "Türkçe",
    "ru-RU": "Русский",
    "ar-SA": "العربية",
    "hi-IN": "हिंदी",
    "ta-IN": "தமிழ்",
    "te-IN": "తెలుగు",
    "zh-CN": "中文 (普通话)",
    "zh-HK": "中文 (粵語)",
    "zh-TW": "中文 (國語)",
    "ko-KR": "한국어",
    "th-TH": "ไทย",
}

LANGUAGE_CODES = {
    "ja-JP": "jpn",
    "en-US": "eng",
    "en-IN": "eng",
    "id-ID": "ind",
    "ms-MY": "msa",
    "ca-ES": "cat",
    "de-DE": "deu",
    "es-419": "spa",
    "es-ES": "spa",
    "fr-FR": "fra",
    "it-IT": "ita",
    "pl-PL": "pol",
    "pt-BR": "por",
    "pt-PT": "por",
    "vi-VN": "vie",
    "tr-TR": "tur",
    "ru-RU": "rus",
    "ar-SA": "ara",
    "hi-IN": "hin",
    "ta-IN": "tam",
    "te-IN": "tel",
    "zh-CN": "zho",
    "zh-HK": "zho",
    "zh-TW": "zho",
    "ko-KR": "kor",
    "th-TH": "tha",
}


def track_title(locale: str) -> str:
    """get the language name from the locale code"""
    if locale.endswith("-cc"):
        base = locale[:-3]  # strip '-cc'
        base_name = LANGUAGE_NAMES.get(base, base)
        return f"{base_name} (CC)"
    return LANGUAGE_NAMES.get(locale, locale)


def locale_base(locale: str) -> str:
    """Return the base locale, stripping any '-cc' suffix."""
    return locale[:-3] if locale.endswith("-cc") else locale


def sanitize_filename(s: str) -> str:
    """clean up string so the OS doesn't complain about bad characters"""
    if not s:
        return "Unknown"

    # replace unicode dashes and quotes with clean ascii equivalents
    s = s.replace("—", "-").replace("–", "-").replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")

    # Replace colons with clean hyphen separators for Plex and Jellyfin title matching
    s = s.replace(":", " - ")

    # swap illegal chars with underscores
    res = re.sub(r'[\\/*?"<>|\'"`]', "_", s)
    # clean multiple whitespace, underscores, and hyphens
    res = re.sub(r"\s+", " ", res)
    res = re.sub(r"_{2,}", "_", res)
    res = re.sub(r"-\s*-+", "-", res)

    return res.strip(" ._-") or "Unknown"


def resolve_season_folder(
    series_title: str,
    season_number: int,
    season_title: str = "",
) -> str:
    """
    Resolves the folder name for a season or story arc.
    If Crunchyroll provides a distinct arc name (e.g. 'Mugen Train Arc', 'Entertainment District Arc', 'OADs'),
    uses that cleaned arc name. Otherwise falls back to standard 'Season XX'.
    """
    clean = (season_title or "").strip()
    if series_title and clean.lower().startswith(series_title.lower()):
        clean = clean[len(series_title):].strip(" :-–—")

    # Strip any trailing dub/audio tags like (English Dub), [English Dub], (Sub), etc.
    clean_no_dub = re.sub(
        r"\s*[\(\[](?:dub|audio|sub|simul|cut|russian|german|spanish|french|portuguese|hindi|arabic|castilian|italian|english)[^\)\]]*[\)\]]",
        "",
        clean,
        flags=re.I,
    ).strip(" :-–—")
    lower_no_dub = clean_no_dub.lower()

    # If formatted as "Season X: Arc Name" or "Season X - Arc Name", extract the Arc Name
    m = re.match(r"^season\s*\d+\s*[:\-–—]\s*(.+)$", clean_no_dub, flags=re.I)
    if m:
        clean_no_dub = m.group(1).strip(" :-–—")
        lower_no_dub = clean_no_dub.lower()

    # If it is empty, or merely a generic "Season X" / "S1" label, use formatted Season XX
    if not clean_no_dub or re.fullmatch(r"season\s*\d+", lower_no_dub) or re.fullmatch(r"s\d+", lower_no_dub):
        return f"Season {season_number:02d}"

    return sanitize_filename(clean_no_dub)


class OutputPathInfo(NamedTuple):
    output_dir: str
    filename: str
    output_filename: str
    stem: str
    original_filename: str
    original_stem: str


def build_output_path(
    base_dir: str,
    series_title: str,
    season_folder: str,
    season_num: int,
    ep_num: int,
    ep_title: str,
    quality_tag: str,
    ext: str,
    ep_subfolder: Optional[bool] = None,
    max_path_length: Optional[int] = None,
    max_component_length: int = 255,
    temp_suffix_buffer: int = 21,
) -> OutputPathInfo:
    """
    Constructs safe output directory, filename, and full path respecting filesystem limits.
    On Windows (or when max_path_length <= 260), ensures that the full path plus any
    temporary suffixes derived during muxing (e.g. '.tmp.mkv.chapters.txt' or '.tmp.mkv')
    strictly do not exceed MAX_PATH (259 characters).

    If the full path or filename exceeds the budget:
      1. Shortens ep_title first.
      2. If ep_title is exhausted or omitted, shortens series_title in the filename.
      3. Preserves season/episode numbers (e.g. 'S01E08'), quality tags, and file extension.
      4. Preserves short paths completely untouched so existing downloads remain 100% compatible.
    """
    if max_path_length is None:
        max_path = 259 if (os.name == "nt" or sys.platform == "win32") else 4096
    else:
        max_path = max_path_length

    base_dir = os.path.abspath(os.path.expanduser((base_dir or ".").strip()))
    clean_series = sanitize_filename(series_title or "Unknown")
    clean_ep = sanitize_filename(ep_title or "Unknown")
    season_ep_tag = f"S{season_num:02d}E{ep_num:02d}"
    fixed_season_ep = f" - {season_ep_tag}"
    fixed_suffix = f"{quality_tag}{ext}"

    orig_stem = f"{clean_series}{fixed_season_ep} - {clean_ep}"
    orig_filename = f"{orig_stem}{fixed_suffix}"

    if ep_subfolder:
        output_dir = os.path.join(base_dir, clean_series, season_folder, orig_stem)
    else:
        output_dir = os.path.join(base_dir, clean_series, season_folder)

    orig_full_path = os.path.join(output_dir, orig_filename)

    needs_shortening = (
        (len(orig_full_path) + temp_suffix_buffer > max_path)
        or (len(orig_filename) + temp_suffix_buffer > max_component_length)
    )

    if not needs_shortening:
        return OutputPathInfo(
            output_dir=output_dir,
            filename=orig_filename,
            output_filename=orig_full_path,
            stem=orig_stem,
            original_filename=orig_filename,
            original_stem=orig_stem,
        )

    # Standalone mode where an episode subfolder is created
    if ep_subfolder:
        base_parent = os.path.join(base_dir, clean_series, season_folder)
        rem = max_path - len(base_parent) - 2 - len(fixed_suffix) - temp_suffix_buffer
        allowed_stem_len = max(len(season_ep_tag), rem // 2)
        pfx = f"{clean_series}{fixed_season_ep} - "
        if allowed_stem_len > len(pfx):
            short_ep = clean_ep[: allowed_stem_len - len(pfx)].rstrip(" ._-")
            stem = f"{clean_series}{fixed_season_ep} - {short_ep}" if short_ep else f"{clean_series}{fixed_season_ep}"
        elif allowed_stem_len >= len(f"{clean_series}{fixed_season_ep}"):
            stem = f"{clean_series}{fixed_season_ep}"
        else:
            budget_series = allowed_stem_len - len(fixed_season_ep)
            if budget_series > 0:
                short_s = clean_series[:budget_series].rstrip(" ._-")
                stem = f"{short_s}{fixed_season_ep}" if short_s else season_ep_tag
            else:
                stem = season_ep_tag
        output_dir = os.path.join(base_parent, stem)
        filename = f"{stem}{fixed_suffix}"
        full_path = os.path.join(output_dir, filename)
        return OutputPathInfo(
            output_dir=output_dir,
            filename=filename,
            output_filename=full_path,
            stem=stem,
            original_filename=orig_filename,
            original_stem=orig_stem,
        )

    # Standard layout (no ep_subfolder)
    min_filename_budget = len(fixed_season_ep) + len(fixed_suffix) + 10
    if max_path - len(output_dir) - 1 - temp_suffix_buffer < min_filename_budget:
        base_season_len = len(os.path.join(base_dir, "", season_folder))
        allowed_folder_len = max_path - base_season_len - 1 - min_filename_budget - temp_suffix_buffer
        if allowed_folder_len > 10:
            short_series_folder = clean_series[:allowed_folder_len].rstrip(" ._-")
            output_dir = os.path.join(base_dir, short_series_folder, season_folder)

    max_from_path = max_path - len(output_dir) - 1 - temp_suffix_buffer
    max_from_comp = max_component_length - temp_suffix_buffer
    allowed_filename_len = max(len(fixed_suffix) + 7, min(max_from_path, max_from_comp))

    prefix = f"{clean_series}{fixed_season_ep} - "
    budget_for_ep = allowed_filename_len - len(prefix) - len(fixed_suffix)

    if budget_for_ep > 0:
        short_ep = clean_ep[:budget_for_ep].rstrip(" ._-")
        if short_ep:
            stem = f"{clean_series}{fixed_season_ep} - {short_ep}"
            filename = f"{stem}{fixed_suffix}"
        else:
            stem = f"{clean_series}{fixed_season_ep}"
            filename = f"{stem}{fixed_suffix}"
    elif len(f"{clean_series}{fixed_season_ep}{fixed_suffix}") <= allowed_filename_len:
        stem = f"{clean_series}{fixed_season_ep}"
        filename = f"{stem}{fixed_suffix}"
    else:
        budget_for_series = allowed_filename_len - len(fixed_season_ep) - len(fixed_suffix)
        if budget_for_series > 0:
            short_series = clean_series[:budget_for_series].rstrip(" ._-")
            if short_series:
                stem = f"{short_series}{fixed_season_ep}"
                filename = f"{stem}{fixed_suffix}"
            else:
                stem = season_ep_tag
                filename = f"{stem}{fixed_suffix}"
        else:
            stem = season_ep_tag
            if len(f"{stem}{fixed_suffix}") <= allowed_filename_len:
                filename = f"{stem}{fixed_suffix}"
            else:
                filename = f"{stem}{ext}"

    full_path = os.path.join(output_dir, filename)
    return OutputPathInfo(
        output_dir=output_dir,
        filename=filename,
        output_filename=full_path,
        stem=stem,
        original_filename=orig_filename,
        original_stem=orig_stem,
    )
