import re

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
    return LANGUAGE_NAMES.get(locale, locale)


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

