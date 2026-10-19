import json
import time
from typing import List, Optional, Tuple, Dict, Any
from urllib.parse import quote, urlparse, urlunparse, urlencode, parse_qs

import requests
from .http_client import CrunchyrollHttpClient
from .types import (
    DubVersion,
    EpisodeInfo,
    EpisodeMetadata,
    PlaybackStream,
    Season,
    SeasonEpisode,
    Subtitle,
)


_SUBTITLE_LOCALE_ALIASES = {
    "en": "en-US",
    "de": "de-DE",
    "fr": "fr-FR",
    "es": "es-419",
    "pt": "pt-BR",
    "id": "id-ID",
    "vi": "vi-VN",
    "th": "th-TH",
    "english": "en-US",
    "bahasa indonesia": "id-ID",
    "tiếng việt": "vi-VN",
    "tieng viet": "vi-VN",
    "ไทย": "th-TH",
    "thai": "th-TH",
}

def _subtitle_locale(raw_key: object, raw_language: object) -> str:
    """Return a stable locale key from a subtitle API record."""
    key = str(raw_key or "").strip()
    language = str(raw_language or "").strip()
    key_lower = key.lower()
    language_lower = language.lower()

    if key_lower in {"none", "und", "unknown"} or not key:
        return _SUBTITLE_LOCALE_ALIASES.get(language_lower, "")
    if key_lower in _SUBTITLE_LOCALE_ALIASES:
        return _SUBTITLE_LOCALE_ALIASES[key_lower]
    return key



def parse_url_type(url: str) -> Tuple[str, str]:
    """figure out if the url is an episode, season, or series"""
    clean_url = url.split("?")[0].split("#")[0].strip()
    parts = [p for p in clean_url.split("/") if p]

    # Handle direct raw series/episode ID (e.g. GVDHX8QNW)
    if len(parts) == 1 and "/" not in clean_url and "." not in clean_url and len(clean_url) >= 8:
        return ("series", clean_url)

    # Handle two-part shorthand like "series/GVDHX8QNW" or "watch/GEVUZM77J"
    if len(parts) == 2 and parts[0] in ("series", "season", "episode", "watch"):
        return ("episode" if parts[0] == "watch" else parts[0], parts[1])

    for i, part in enumerate(parts):
        if part in ("watch", "episode") and i + 1 < len(parts):
            return ("episode", parts[i + 1])
        elif part == "series" and i + 1 < len(parts):
            return ("series", parts[i + 1])
        elif part == "season" and i + 1 < len(parts):
            return ("season", parts[i + 1])

    if len(parts) >= 4:
        c_type = parts[2]
        c_id = parts[3]
        if c_type == "watch":
            return ("episode", c_id)
        elif c_type == "series":
            return ("series", c_id)
        elif c_type == "season":
            return ("season", c_id)

    raise ValueError(f"Unable to parse Crunchyroll URL: {url}")


def _parse_playback_response(data: Dict[str, Any], debug: bool = False) -> PlaybackStream:
    """Parse playback JSON payload into a PlaybackStream."""
    manifest_url = str(data.get("url", "") or "").strip()
    if not manifest_url:
        hardsubs = data.get("hardsubs") or data.get("hardSubs") or {}
        if isinstance(hardsubs, dict):
            if "en-US" in hardsubs and isinstance(hardsubs["en-US"], dict):
                manifest_url = str(hardsubs["en-US"].get("url", "") or "").strip()
            elif "" in hardsubs and isinstance(hardsubs[""], dict):
                manifest_url = str(hardsubs[""].get("url", "") or "").strip()
            elif hardsubs:
                for entry in hardsubs.values():
                    if isinstance(entry, dict) and entry.get("url"):
                        manifest_url = str(entry.get("url", "") or "").strip()
                        break

    if debug:
        print("\n--- DEBUG PLAYBACK STREAM JSON ---")
        print(json.dumps(data, indent=2))

    subtitles: Dict[str, Subtitle] = {}

    def _parse_subtitle_entries(raw: Any, is_cc: bool) -> None:
        """Parse a subtitles or captions dict/list from the API into `subtitles`."""
        if isinstance(raw, dict):
            for lang, s_info in raw.items():
                if not isinstance(s_info, dict):
                    continue
                subtitle_url = str(s_info.get("url", "") or "").strip()
                parsed_url = urlparse(subtitle_url)
                if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                    # Crunchyroll may include placeholder entries such as
                    # "none" with no URL; they are not downloadable tracks.
                    continue
                resolved_lang = s_info.get("language") or lang
                locale = _subtitle_locale(lang, resolved_lang)
                if not locale:
                    continue
                is_cc_entry = is_cc or bool(s_info.get("closed_caption") or s_info.get("closedCaption"))
                key = f"{locale}-cc" if is_cc_entry else locale
                subtitles[key] = Subtitle(
                    language=str(resolved_lang or locale),
                    url=subtitle_url,
                    is_cc=is_cc_entry,
                )
        elif isinstance(raw, list):
            for s_info in raw:
                if not isinstance(s_info, dict):
                    continue
                subtitle_url = str(s_info.get("url", "") or "").strip()
                parsed_url = urlparse(subtitle_url)
                if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                    continue
                raw_lang = s_info.get("language")
                locale = _subtitle_locale(
                    s_info.get("locale") or s_info.get("lang") or raw_lang,
                    raw_lang,
                )
                if locale:
                    is_cc_entry = is_cc or bool(s_info.get("closed_caption") or s_info.get("closedCaption"))
                    key = f"{locale}-cc" if is_cc_entry else locale
                    subtitles[key] = Subtitle(
                        language=str(raw_lang or locale),
                        url=subtitle_url,
                        is_cc=is_cc_entry,
                    )

    # Regular subtitle tracks (usually .ass with full styling)
    _parse_subtitle_entries(data.get("subtitles", {}), is_cc=False)
    # Closed-caption tracks (usually .vtt, for hearing-impaired viewers)
    _parse_subtitle_entries(data.get("captions", {}), is_cc=True)

    token = str(data.get("token") or data.get("playbackToken") or data.get("playback_token") or "")
    return PlaybackStream(manifest_url=manifest_url, subtitles=subtitles, token=token)


# HTTP statuses on which Crunchyroll reports the KAT-3002 stream-limit error.
_STREAM_LIMIT_STATUSES = (400, 403, 409, 429)


def _is_stream_limit_response(response) -> bool:
    """Return True only for genuine KAT-3002 stream-limit responses.

    A bare "3002" substring on a 200 OK body (episode title, GUID, timestamp)
    must NOT trigger a session purge, so both the status code and a
    structured error marker are required.
    """
    if getattr(response, "status_code", None) not in _STREAM_LIMIT_STATUSES:
        return False
    text = getattr(response, "text", "") or ""
    return (
        "KAT-3002" in text
        or '"code": 3002' in text
        or '"code":"KAT-3002"' in text
    )


def get_episode(
    client: CrunchyrollHttpClient,
    content_id: str,
    debug: bool = False,
    playback_id: Optional[str] = None,
    queue: int = 0,
) -> PlaybackStream:
    """Grab a stream URL and token from Android TV play service with Web fallback."""
    clean_id = str(content_id).strip()
    quoted_content_id = quote(clean_id, safe="")
    timeout = getattr(client, "DEFAULT_REQUEST_TIMEOUT", 20)
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [playback] "
        f"Request started for content {clean_id} "
        f"(timeout={timeout}s)...",
        flush=True,
    )

    # 1. Prioritize official Crunchyroll Android TV play service
    android_url = (
        f"https://cr-play-service.prd.crunchyrollsvc.com/v3/{quoted_content_id}/tv/android_tv/play?queue={queue}"
    )
    android_headers = {
        "User-Agent": "Crunchyroll/ANDROIDTV/3.70.0_22358 (Android 12; en-US; SHIELD Android TV Build/SR1A.220624.014)",
    }
    raw_android_token = getattr(client, "android_token", None)
    if isinstance(raw_android_token, str) and raw_android_token.strip():
        android_token = raw_android_token.strip()
    else:
        android_token = getattr(client, "token", None)

    if android_token:
        token_str = str(android_token).strip()
        if token_str:
            android_headers["Authorization"] = f"Bearer {token_str}"

    started_at = time.monotonic()
    try:
        response = client.do_request("GET", android_url, headers=android_headers)
        if _is_stream_limit_response(response):
            print("[playback] Stream limit detected (3002) during Android TV request; auto-purging orphaned sessions...", flush=True)
            purge_orphan_streams(client, all_devices=True)
            time.sleep(1.0)
            response = client.do_request("GET", android_url, headers=android_headers)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Playback response was not a JSON object")
        stream = _parse_playback_response(data, debug=debug)
        if not stream.manifest_url:
            raise RuntimeError("Playback response contained no manifest URL")
        elapsed = time.monotonic() - started_at
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [playback] "
            f"Response received for content {clean_id}: "
            f"HTTP {response.status_code} after {elapsed:.1f}s",
            flush=True,
        )
        return stream
    except Exception as exc:
        reason = " ".join(str(exc).split()) if str(exc).strip() else type(exc).__name__
        print(
            f"[playback] Android TV playback failed ({reason}); falling back to web endpoint...",
            flush=True,
        )

    # 2. Fallback to web endpoint
    web_url = f"https://www.crunchyroll.com/playback/v3/{quoted_content_id}/web/chrome/play"
    web_started_at = time.monotonic()
    try:
        response = client.do_request("GET", web_url)
        if _is_stream_limit_response(response):
            print("[playback] Stream limit detected (3002) during web playback request; auto-purging orphaned sessions...", flush=True)
            purge_orphan_streams(client, all_devices=True)
            time.sleep(1.0)
            response = client.do_request("GET", web_url)
    except Exception as exc:
        elapsed = time.monotonic() - web_started_at
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [playback] "
            f"Request failed for content {clean_id} "
            f"after {elapsed:.1f}s: {type(exc).__name__}: {exc}",
            flush=True,
        )
        raise

    elapsed = time.monotonic() - web_started_at
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [playback] "
        f"Response received for content {clean_id}: "
        f"HTTP {response.status_code} after {elapsed:.1f}s",
        flush=True,
    )
    response.raise_for_status()

    try:
        data = response.json()
    except Exception:
        raise

    if not isinstance(data, dict):
        raise RuntimeError("Playback response was not a JSON object")

    return _parse_playback_response(data, debug=debug)


def _convert_download_to_playback(download_url: str, play_url: str) -> str:
    """Normalize mobile download manifest URL into standard playback format.

    The /download endpoint returns a manifest URL whose path contains
    '/manifest/download/' with a 'downloadGuid' query param.
    We patch it to look like a standard /play manifest URL so that the
    existing DASH/Widevine pipeline works unchanged:

      /manifest/download/ → /manifest/
      downloadGuid=...    → playbackGuid=<token from /play response>
    """
    try:
        parsed = urlparse(download_url)
        play_parsed = urlparse(play_url)

        new_path = parsed.path.replace("/manifest/download/", "/manifest/")

        qs = parse_qs(parsed.query, keep_blank_values=True)
        play_qs = parse_qs(play_parsed.query, keep_blank_values=True)

        playback_guid = play_qs.get("playbackGuid", [None])[0]
        if playback_guid:
            qs.pop("downloadGuid", None)
            qs["playbackGuid"] = [playback_guid]
        elif "downloadGuid" in qs:
            qs["playbackGuid"] = [qs.pop("downloadGuid")[0]]

        new_query = urlencode(qs, doseq=True)
        return urlunparse((
            parsed.scheme, parsed.netloc, new_path,
            parsed.params, new_query, parsed.fragment
        ))
    except Exception:
        return download_url


def get_episode_download(
    client: CrunchyrollHttpClient,
    content_id: str,
    play_stream: "PlaybackStream",
    debug: bool = False,
    client_type: str = "android/phone",
    video_quality: Optional[str] = None,
) -> "PlaybackStream":
    """Fetch the mobile /download endpoint for high-speed CDN routing.

    Unlike the standard /play endpoint which is subject to a ~1 MB/s CDN
    token-bucket rate limit, the mobile /download path serves segments from a
    dedicated distribution profile not subject to the same throttling.

    Supported client_type values:
      - "android/phone"   — Android phone client (default)
      - "android/tablet"  — Android tablet client
      - "tv/android_tv"   — Android TV (standard play stream)

    If the /download request fails (HTTP error or no manifest URL),
    returns the original play_stream unchanged so the caller can proceed
    with the standard manifest.
    """
    clean_id = str(content_id).strip()
    quoted_content_id = quote(clean_id, safe="")

    res_val = str(video_quality or "").lower().replace("p", "").strip()
    if not res_val or not res_val.isdigit():
        res_val = "720"

    download_url = (
        f"https://www.crunchyroll.com/playback/v3/{quoted_content_id}/{client_type}/download?resolution={res_val}"
    )

    android_headers: Dict[str, str] = {}

    # Use modern Android mobile client User-Agent for phone/tablet client paths
    if "phone" in client_type or "tablet" in client_type:
        android_headers["User-Agent"] = "Crunchyroll/3.118.0 Android/14 okhttp/5.3.2"
    else:
        android_headers["User-Agent"] = (
            "Crunchyroll/ANDROIDTV/3.70.0_22358 (Android 12; en-US; SHIELD Android TV Build/SR1A.220624.014)"
        )

    # Authenticate with android token if available, else fall back to web token (etp_rt)
    raw_android_token = getattr(client, "android_token", None)
    if isinstance(raw_android_token, str) and raw_android_token.strip():
        android_headers["Authorization"] = f"Bearer {raw_android_token.strip()}"
    else:
        web_token = getattr(client, "token", None)
        if not web_token and getattr(client, "etp_rt", None):
            try:
                client.refresh_token()
                web_token = getattr(client, "token", None)
            except Exception:
                pass
        if web_token:
            android_headers["Authorization"] = f"Bearer {str(web_token).strip()}"

    print(
        f"[playback] Requesting /download endpoint for {clean_id} via {client_type}...",
        flush=True,
    )

    try:
        response = client.do_request("GET", download_url, headers=android_headers)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Download response was not a JSON object")

        dl_stream = _parse_playback_response(data, debug=debug)
        if not dl_stream.manifest_url:
            raise RuntimeError("Download response contained no manifest URL")

        # Patch the manifest URL: /download/ → /play/ path, swap downloadGuid → playbackGuid
        patched_url = _convert_download_to_playback(dl_stream.manifest_url, play_stream.manifest_url)
        print(
            f"[playback] /download succeeded; patched manifest URL obtained. "
            f"(token borrowed from /play session)",
            flush=True,
        )

        # Preserve all subtitle tracks from standard /play and overlay any from /download
        merged_subtitles = dict(play_stream.subtitles or {})
        if dl_stream.subtitles:
            merged_subtitles.update(dl_stream.subtitles)

        return PlaybackStream(
            manifest_url=patched_url,
            subtitles=merged_subtitles,
            token=play_stream.token,  # CRITICAL: reuse /play token, not /download token
        )

    except Exception as exc:
        print(
            f"[playback] /download endpoint failed ({exc}); "
            f"falling back to standard /play manifest.",
            flush=True,
        )
        return play_stream



def get_episode_info(
    client: CrunchyrollHttpClient, content_id: str
) -> EpisodeInfo:
    """get metadata (title, dubs, etc) for an episode"""
    url = f"https://www.crunchyroll.com/content/v2/cms/objects/{content_id}"
    resp = client.do_request("GET", url)
    resp.raise_for_status()

    data = resp.json()
    items = data.get("data", [])
    if not items:
        raise RuntimeError(f"No object data returned for content_id {content_id}")

    obj = items[0]
    title = obj.get("title", "")
    ep_meta_raw = obj.get("episode_metadata", {})

    versions_raw = ep_meta_raw.get("versions", [])
    versions = [
        DubVersion(
            guid=v.get("guid", ""),
            media_guid=v.get("media_guid", ""),
            season_guid=v.get("season_guid", ""),
            audio_locale=v.get("audio_locale", ""),
            locale=v.get("locale", ""),
        )
        for v in versions_raw
    ]

    ep_meta = EpisodeMetadata(
        series_title=ep_meta_raw.get("series_title", ""),
        season_number=ep_meta_raw.get("season_number", 0),
        episode_number=ep_meta_raw.get("episode_number", 0),
        audio_locale=ep_meta_raw.get("audio_locale", ""),
        versions=versions,
        availability_starts=ep_meta_raw.get("availability_starts", ""),
        season_title=ep_meta_raw.get("season_title", ""),
    )

    subs = {}
    return EpisodeInfo(episode_metadata=ep_meta, title=title, subtitles=subs)


_CMS_PAGE_LIMIT = 100
_CMS_MAX_PAGES = 25


def _paginate_cms(
    client: CrunchyrollHttpClient,
    base_url: str,
    limit: int = _CMS_PAGE_LIMIT,
    max_pages: int = _CMS_MAX_PAGES,
) -> List[Dict[str, Any]]:
    """Fetch all pages of a Crunchyroll CMS listing endpoint.

    The CMS API caps each response at `limit` records, so series/seasons with
    more than one page of episodes would otherwise be silently truncated.
    The caller must supply `base_url` with its query parameters already set;
    `start` and `limit` are appended here.
    """
    items: List[Dict[str, Any]] = []
    start = 0

    for _ in range(max_pages):
        page_url = f"{base_url}&start={start}&limit={limit}"
        resp = client.do_request("GET", page_url)
        resp.raise_for_status()

        data = resp.json()
        page = data.get("data", []) or []
        items.extend(page)

        if not page or len(page) < limit:
            break

        total = data.get("total")
        try:
            total_val = int(total) if total is not None else None
        except (TypeError, ValueError):
            total_val = None
        if total_val is not None and len(items) >= total_val:
            break

        start += limit

    return items


def get_seasons(
    client: CrunchyrollHttpClient,
    series_id: str,
    audio_locale: str = "ja-JP",
    sub_locale: str = "en-US",
) -> List[Season]:
    """list seasons for a series"""
    base_url = (
        f"https://www.crunchyroll.com/content/v2/cms/series/{series_id}/seasons"
        f"?preferred_audio_language={audio_locale}&locale={sub_locale}"
    )

    items = _paginate_cms(client, base_url)

    seasons = []
    for item in items:
        seasons.append(
            Season(
                id=item.get("id", ""),
                season_number=item.get("season_number", 0),
                audio_locale=item.get("audio_locale", ""),
                title=item.get("title", ""),
            )
        )
    seasons.sort(key=lambda s: (s.season_number if s.season_number > 0 else 999, s.title))
    return seasons


def get_season_episodes(
    client: CrunchyrollHttpClient,
    season_id: str,
    audio_locale: str = "ja-JP",
    sub_locale: str = "en-US",
) -> List[SeasonEpisode]:
    """list all episodes in a season"""
    base_url = (
        f"https://www.crunchyroll.com/content/v2/cms/seasons/{season_id}/episodes"
        f"?preferred_audio_language={audio_locale}&locale={sub_locale}"
    )

    items = _paginate_cms(client, base_url)

    episodes = []
    for seq_idx, item in enumerate(items, start=1):
        ep_meta_raw = item.get("episode_metadata", {})
        versions_raw = ep_meta_raw.get("versions", [])
        versions = [
            DubVersion(
                guid=v.get("guid", ""),
                media_guid=v.get("media_guid", ""),
                season_guid=v.get("season_guid", ""),
                audio_locale=v.get("audio_locale", ""),
                locale=v.get("locale", ""),
            )
            for v in versions_raw
        ]

        ep_num_val = (
            ep_meta_raw.get("episode_number")
            if ep_meta_raw.get("episode_number") is not None
            else item.get("episode_number")
        )
        if ep_num_val is None:
            ep_num_val = item.get("sequence_number", seq_idx)

        try:
            ep_num = int(float(ep_num_val))
        except Exception:
            ep_num = seq_idx

        season_num_val = (
            ep_meta_raw.get("season_number")
            if ep_meta_raw.get("season_number") is not None
            else item.get("season_number", 1)
        )
        try:
            season_num = int(float(season_num_val))
        except Exception:
            season_num = 1

        episodes.append(
            SeasonEpisode(
                id=item.get("id", ""),
                title=item.get("title", f"Episode {ep_num}"),
                season_number=season_num,
                episode_number=ep_num,
                series_title=ep_meta_raw.get("series_title", item.get("series_title", "")),
                audio_locale=ep_meta_raw.get("audio_locale", item.get("audio_locale", "")),
                versions=versions,
                availability_starts=ep_meta_raw.get("availability_starts", ""),
                season_id=season_id,
                season_title=ep_meta_raw.get("season_title", item.get("season_title", "")),
            )
        )

    episodes.sort(key=lambda e: (e.season_number, e.episode_number if e.episode_number > 0 else 9999))
    return episodes


def get_series(
    client: CrunchyrollHttpClient,
    series_id: str,
    audio_locale: str = "ja-JP",
    sub_locale: str = "en-US",
) -> Dict[str, Any]:
    """fetch series metadata, seasons, and episodes in one go"""
    url = (
        f"https://www.crunchyroll.com/content/v2/cms/series/{series_id}"
        f"?preferred_audio_language={audio_locale}&locale={sub_locale}"
    )
    resp = client.do_request("GET", url)
    series_meta = {}
    if resp.status_code == 200:
        data = resp.json()
        items = data.get("data", [])
        if items:
            series_meta = items[0]

    seasons = get_seasons(client, series_id, audio_locale, sub_locale)
    all_episodes: List[SeasonEpisode] = []

    for season in seasons:
        eps = get_season_episodes(client, season.id, audio_locale, sub_locale)
        all_episodes.extend(eps)

    poster = ""
    images = series_meta.get("images", {})
    if images and isinstance(images, dict):
        for p_type in ("poster_tall", "poster_wide", "promo_image"):
            groups = images.get(p_type, [])
            if groups and isinstance(groups, list):
                for group in groups:
                    if isinstance(group, list):
                        candidates = [c for c in group if isinstance(c, dict) and c.get("source")]
                        if candidates:
                            preferred = [c for c in candidates if 200 <= c.get("width", 0) <= 600]
                            poster = preferred[0]["source"] if preferred else candidates[-1]["source"]
                            break
                if poster:
                    break

    return {
        "id": series_id,
        "title": series_meta.get("title", ""),
        "description": series_meta.get("description", ""),
        "poster": poster,
        "seasons": seasons,
        "episodes": all_episodes,
    }


def search_series(
    client: CrunchyrollHttpClient,
    query: str,
    limit: int = 15,
    locale: str = "en-US",
) -> List[Dict[str, Any]]:
    """Search Crunchyroll for anime series matching `query`.

    Returns a list of series items with id, title, description, poster, season/episode counts, etc.
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    # Ensure client has an active token
    if not client.token:
        try:
            from .auth import get_guest_token
            client.token = get_guest_token()
        except Exception:
            pass

    encoded_q = quote(clean_q)
    target_limit = max(1, min(50, limit))

    # Query discover search without type restriction to retrieve top_results, series, and movie_listing
    url = f"https://www.crunchyroll.com/content/v2/discover/search?q={encoded_q}&n={target_limit}&locale={locale}"
    resp = client.do_request("GET", url)
    if resp.status_code != 200:
        alt_url = f"https://beta-api.crunchyroll.com/content/v2/discover/search?q={encoded_q}&n={target_limit}&locale={locale}"
        resp = client.do_request("GET", alt_url)
        if resp.status_code != 200:
            raise RuntimeError(f"Crunchyroll search failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    results: List[Dict[str, Any]] = []
    seen_ids = set()

    for section in data.get("data", []):
        for item in section.get("items", []):
            item_id = item.get("id")
            if not item_id or item_id in seen_ids:
                continue

            item_type = item.get("type", "series")
            # Only include series and movie_listing items that can be fetched as series
            if item_type not in ("series", "movie_listing"):
                continue

            seen_ids.add(item_id)
            meta = item.get("series_metadata", {}) or {}
            images = item.get("images", {}) or {}

            # Poster resolution picker: prioritize ~240-480px tall posters
            poster_url = ""
            for p_type in ("poster_tall", "poster_wide", "promo_image"):
                groups = images.get(p_type, [])
                if groups and isinstance(groups, list):
                    for group in groups:
                        if isinstance(group, list):
                            candidates = [c for c in group if isinstance(c, dict) and c.get("source")]
                            if candidates:
                                preferred = [c for c in candidates if 200 <= c.get("width", 0) <= 600]
                                poster_url = preferred[0]["source"] if preferred else candidates[-1]["source"]
                                break
                    if poster_url:
                        break

            season_cnt = meta.get("season_count")
            if season_cnt is None:
                season_cnt = 1 if item_type == "movie_listing" else 0

            ep_cnt = meta.get("episode_count")
            if ep_cnt is None:
                ep_cnt = 1 if item_type == "movie_listing" else 0

            results.append({
                "id": item_id,
                "type": item_type,
                "title": item.get("title", ""),
                "description": item.get("description", "") or item.get("promo_description", ""),
                "slug": item.get("slug_title", "") or item.get("slug", ""),
                "poster": poster_url,
                "season_count": int(season_cnt),
                "episode_count": int(ep_cnt),
                "is_mature": bool(meta.get("is_mature", False)),
                "is_subbed": bool(meta.get("is_subbed", True)),
                "is_dubbed": bool(meta.get("is_dubbed", False)),
                "year": meta.get("series_launch_year"),
                "audio_locales": meta.get("audio_locales", []),
                "subtitle_locales": meta.get("subtitle_locales", []),
            })

            if len(results) >= target_limit:
                break
        if len(results) >= target_limit:
            break

    return results


def delete_stream(
    client: CrunchyrollHttpClient, content_id: str, video_token: str
) -> bool:
    """Release a playback session using its content ID and playback token.

    Tries the official Android TV play service first (where play sessions are initiated),
    and falls back to the web playback endpoint. Cleanup is intentionally idempotent:
    an expired or already-removed playback session is considered successfully cleaned up.
    """
    clean_content_id = str(content_id or "").strip()
    clean_token = str(video_token or "").strip()
    if not clean_content_id or not clean_token:
        return False

    q_cid = quote(clean_content_id, safe="")
    q_tok = quote(clean_token, safe="")

    # 1. Try Android TV play service endpoint
    tv_headers = {
        "Accept": "*/*",
        "User-Agent": "Crunchyroll/ANDROIDTV/3.70.0_22358 (Android 12; en-US; SHIELD Android TV Build/SR1A.220624.014)",
    }
    raw_android_token = getattr(client, "android_token", None)
    token = raw_android_token or getattr(client, "token", None)
    if token:
        tv_headers["Authorization"] = f"Bearer {str(token).strip()}"

    tv_url = f"https://cr-play-service.prd.crunchyrollsvc.com/v1/token/{q_cid}/{q_tok}"
    try:
        resp = client.do_request("DELETE", tv_url, headers=tv_headers)
        if 200 <= resp.status_code < 300 or resp.status_code in {401, 404, 410}:
            return True
    except Exception:
        pass

    # 2. Fallback to web playback endpoint
    web_url = f"https://www.crunchyroll.com/playback/v1/token/{q_cid}/{q_tok}"
    headers = {"Accept": "*/*"}
    try:
        resp = client.do_request("DELETE", web_url, headers=headers)
        return 200 <= resp.status_code < 300 or resp.status_code in {401, 404, 410}
    except Exception:
        return False


def purge_orphan_streams(
    client: CrunchyrollHttpClient,
    device_id: Optional[str] = None,
    all_devices: bool = False,
) -> int:
    """Query and delete dangling playback sessions on Crunchyroll's servers.

    Prevents accounts from hitting concurrent playback limits (KAT-3002) caused
    by crashed processes, unhandled interrupts, or leaked subtitle queries.
    By default, only deletes sessions created by this client's deviceId to avoid
    interrupting other active streams on the same account.
    """
    from .auth import get_device_id

    target_device_id = device_id or getattr(client, "device_id", None)
    if not target_device_id:
        try:
            target_device_id = get_device_id()
        except Exception:
            target_device_id = ""

    headers = {
        "Accept": "*/*",
        "User-Agent": "Crunchyroll/ANDROIDTV/3.70.0_22358 (Android 12; en-US; SHIELD Android TV Build/SR1A.220624.014)",
    }
    raw_android_token = getattr(client, "android_token", None)
    token = raw_android_token or getattr(client, "token", None)
    if not token:
        return 0

    headers["Authorization"] = f"Bearer {str(token).strip()}"

    url = "https://cr-play-service.prd.crunchyrollsvc.com/v1/sessions/streaming"
    try:
        resp = client.do_request("GET", url, headers=headers)
        if resp.status_code != 200:
            return 0

        data = resp.json()
        items = data.get("items", []) if isinstance(data, dict) else []
        deleted_count = 0

        for item in items:
            if item.get("isDeleted"):
                continue
            item_did = item.get("deviceId", "")
            if not all_devices and target_device_id and item_did != target_device_id:
                continue

            cid = item.get("contentId")
            tok = item.get("token")
            if cid and tok:
                if delete_stream(client, cid, tok):
                    deleted_count += 1

        if deleted_count > 0:
            print(f"[sessions] Purged {deleted_count} orphaned streaming session(s) from Crunchyroll.", flush=True)
        return deleted_count
    except Exception as exc:
        print(f"[sessions] Warning: Failed to query/purge active sessions: {exc}", flush=True)
        return 0


def get_episode_chapters(
    content_id: str,
    duration_seconds: Optional[float] = None,
    client: Optional[CrunchyrollHttpClient] = None,
) -> List[Dict[str, Any]]:
    """
    Fetches official chapter/skip-event markers (Intro, Episode, Credits, Preview)
    from Crunchyroll's public CDN API and constructs a continuous chapter timeline.
    """
    if not content_id:
        return []

    cid = str(content_id).strip()
    if "/" in cid:
        cid = cid.rstrip("/").split("/")[-1]

    data = None
    urls = [
        f"https://static.crunchyroll.com/skip-events/production/{cid}.json",
        f"https://static.crunchyroll.com/datalab-intro-v2/{cid}.json",
    ]

    session = getattr(client, "session", None) or requests

    for url in urls:
        try:
            resp = session.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                loaded = resp.json()
                if isinstance(loaded, dict) and loaded:
                    data = loaded
                    break
        except Exception:
            continue

    if not data:
        return []

    raw_events = []
    # 1. New skip-events format (intro, credits, preview, recap)
    for k in ["recap", "intro", "credits", "preview"]:
        item = data.get(k)
        if isinstance(item, dict) and "start" in item and "end" in item:
            try:
                s = float(item["start"])
                e = float(item["end"])
                if e > s >= 0:
                    raw_events.append({"name": k.capitalize(), "start": s, "end": e})
            except (ValueError, TypeError):
                pass

    # 2. Old datalab-intro-v2 format
    if not raw_events and "startTime" in data and "endTime" in data:
        try:
            s = float(data["startTime"])
            e = float(data["endTime"])
            if e > s >= 0:
                raw_events.append({"name": "Intro", "start": s, "end": e})
        except (ValueError, TypeError):
            pass

    if not raw_events:
        return []

    raw_events.sort(key=lambda x: x["start"])

    timeline = []
    current_time = 0.0

    for ev in raw_events:
        # If there is a meaningful gap (> 2.0s) before this event
        if ev["start"] > current_time + 2.0:
            gap_name = "Prologue" if current_time < 1.0 and ev["name"] == "Intro" else "Episode"
            timeline.append({"name": gap_name, "start": current_time, "end": ev["start"]})
            current_time = ev["start"]
        else:
            # Tiny gap <= 2.0s, bridge it to prevent 1-second fragmented chapters
            if timeline:
                timeline[-1]["end"] = ev["start"]
            current_time = ev["start"]

        timeline.append({"name": ev["name"], "start": current_time, "end": ev["end"]})
        current_time = ev["end"]

    # Final segment to total duration
    if duration_seconds and duration_seconds > current_time + 3.0:
        last_name = "Preview" if timeline and timeline[-1]["name"] == "Credits" else "Episode"
        timeline.append({"name": last_name, "start": current_time, "end": float(duration_seconds)})
    elif duration_seconds and timeline:
        timeline[-1]["end"] = max(timeline[-1]["end"], float(duration_seconds))

    return timeline
