import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple
from .http_client import CrunchyrollHttpClient


def _clean_tag(tag: str) -> str:
    """strip xml namespace prefix"""
    return tag.split("}")[-1] if "}" in tag else tag


def parse_manifest(client: CrunchyrollHttpClient, url: str, debug: bool = False) -> ET.Element:
    """fetch and parse dash mpd manifest"""
    resp = client.do_request("GET", url)
    resp.raise_for_status()

    body = resp.text
    if debug:
        print(f"\n[DEBUG Manifest XML]:\n{body}\n")

    root = ET.fromstring(body)
    return root


_WIDEVINE_SCHEME_ID = "urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"


def get_default_kid(element: ET.Element) -> Optional[bytes]:
    """Extract a DASH CENC default_KID from an MPD element or its children."""
    for elem in element.iter():
        for name, value in elem.attrib.items():
            if name.rsplit("}", 1)[-1].lower() != "default_kid":
                continue
            raw = value.replace("-", "").strip()
            try:
                return bytes.fromhex(raw)
            except ValueError:
                continue
    return None


def get_kids(element: ET.Element) -> List[bytes]:
    """Extract every CENC default_KID declared by an MPD element tree."""
    result: List[bytes] = []
    seen = set()
    for elem in element.iter():
        for name, value in elem.attrib.items():
            if name.rsplit("}", 1)[-1].lower() != "default_kid":
                continue
            try:
                kid = bytes.fromhex(value.replace("-", "").strip())
            except ValueError:
                continue
            if kid not in seen:
                result.append(kid)
                seen.add(kid)
    return result


def get_pssh(manifest: ET.Element) -> Optional[str]:
    """dig out the cenc pssh string from the manifest.
    handles all CR MPD variants - some shows put ContentProtection under
    AdaptationSet, others (e.g. Blue Lock) put it directly under Period.
    """

    def _extract_from_cp(cp: ET.Element) -> Optional[str]:
        # check child elements first (e.g. <cenc:pssh> or bare <pssh>)
        for child in cp:
            tag = _clean_tag(child.tag).lower()
            if "pssh" in tag and child.text and child.text.strip():
                return child.text.strip()
        # check attributes for inline pssh value
        for key, val in cp.attrib.items():
            if "pssh" in key.lower() and val.strip():
                return val.strip()
        return None

    # pass 1: prefer the Widevine-specific ContentProtection by schemeIdUri
    for elem in manifest.iter():
        if _clean_tag(elem.tag) == "ContentProtection":
            if elem.attrib.get("schemeIdUri", "").lower() == _WIDEVINE_SCHEME_ID:
                result = _extract_from_cp(elem)
                if result:
                    return result

    # pass 2: fall back to any ContentProtection anywhere in the manifest
    for elem in manifest.iter():
        if _clean_tag(elem.tag) == "ContentProtection":
            result = _extract_from_cp(elem)
            if result:
                return result

    return None


def parse_dash_duration(value: Optional[str]) -> Optional[float]:
    """Parse an ISO-8601 DASH duration such as ``PT23M23.251S``."""
    if not value:
        return None
    match = re.fullmatch(
        r"P(?:([\d.]+)D)?(?:T(?:([\d.]+)H)?(?:([\d.]+)M)?(?:([\d.]+)S)?)?",
        value,
    )
    if not match:
        return None
    days, hours, minutes, seconds = (
        float(part or 0) for part in match.groups()
    )
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _collect_base_urls(rep: ET.Element, adaptation_set: ET.Element) -> List[str]:
    """Collect all unique BaseURL values declared on a Representation or its parent AdaptationSet."""
    urls: List[str] = []
    for child in rep:
        if _clean_tag(child.tag) == "BaseURL" and child.text and child.text.strip():
            u = child.text.strip()
            if u not in urls:
                urls.append(u)
    if not urls:
        for child in adaptation_set:
            if _clean_tag(child.tag) == "BaseURL" and child.text and child.text.strip():
                u = child.text.strip()
                if u not in urls:
                    urls.append(u)
    return urls


def get_available_cdn_mirrors(adaptation_set: ET.Element) -> List[str]:
    """Return all unique CDN BaseURL prefixes declared in an AdaptationSet."""
    mirrors: List[str] = []
    for elem in adaptation_set.iter():
        if _clean_tag(elem.tag) == "BaseURL" and elem.text and elem.text.strip():
            u = elem.text.strip()
            if u not in mirrors:
                mirrors.append(u)
    return mirrors


def get_base_url(
    adaptation_set: ET.Element,
    is_video_set: bool,
    quality: str,
    server_index: int = 0,
) -> Tuple[Optional[str], Optional[str]]:
    """find base url and representation id for target quality, supporting CDN mirror selection"""
    reps = [e for e in adaptation_set if _clean_tag(e.tag) == "Representation"]

    for rep in reps:
        rep_id = rep.attrib.get("id", "")
        height = rep.attrib.get("height")
        bandwidth = rep.attrib.get("bandwidth")

        candidate_urls = _collect_base_urls(rep, adaptation_set)
        base_url = None
        if candidate_urls:
            selected_idx = min(max(0, server_index), len(candidate_urls) - 1)
            base_url = candidate_urls[selected_idx]
            if len(candidate_urls) > 1 and selected_idx > 0:
                print(f"[CDN] Selected mirror #{selected_idx + 1} of {len(candidate_urls)} for {quality}")

        if is_video_set:
            target_height = quality.replace("p", "")
            if height and str(height) == target_height:
                return base_url, rep_id
        else:
            if "audio/" in rep_id and quality in rep_id:
                return base_url, rep_id
            elif bandwidth is not None:
                bw_val = int(bandwidth)
                num = quality.replace("k", "")
                if num == "192" and bw_val >= 192000:
                    return base_url, rep_id
                elif num == "128" and bw_val >= 128000:
                    return base_url, rep_id
                elif num == "96" and bw_val >= 96000:
                    return base_url, rep_id

    if not reps:
        return None, None

    first_rep = reps[0]
    first_id = first_rep.attrib.get("id", "")
    candidate_urls = _collect_base_urls(first_rep, adaptation_set)
    base_url = candidate_urls[min(max(0, server_index), len(candidate_urls) - 1)] if candidate_urls else None
    print(f"Audio quality {quality} not found, deferring to {first_id}")
    return base_url, first_id


def expand_timeline(
    adaptation_set: ET.Element,
    start_number: int = 1,
    period_duration_seconds: Optional[float] = None,
) -> List[int]:
    """Expand a DASH SegmentTimeline into segment numbers.

    DASH ``r=-1`` means repeat until the next explicit segment timestamp (or
    until the period ends). The old implementation treated it as one segment,
    which can omit most of a track and make audio/video durations diverge.
    This function returns URL numbers, so media timestamps remain encoded in
    the fMP4 fragments and are not reconstructed or discarded here.
    """
    segment_template = next(
        (elem for elem in adaptation_set.iter() if _clean_tag(elem.tag) == "SegmentTemplate"),
        None,
    )
    if segment_template is None:
        return []

    timeline_element = next(
        (elem for elem in segment_template if _clean_tag(elem.tag) == "SegmentTimeline"),
        None,
    )
    if timeline_element is None:
        timeline_element = next(
            (elem for elem in adaptation_set.iter() if _clean_tag(elem.tag) == "SegmentTimeline"),
            None,
        )
    if timeline_element is None:
        return []

    s_elements = [
        elem for elem in timeline_element if _clean_tag(elem.tag) == "S"
    ]

    start_num = start_number
    for elem in adaptation_set.iter():
        if _clean_tag(elem.tag) == "SegmentTemplate":
            sn = elem.attrib.get("startNumber")
            if sn:
                try:
                    start_num = int(sn)
                except ValueError:
                    pass
            break

    result: List[int] = []
    seg_num = start_num

    current_time: Optional[int] = None
    try:
        timescale = int(segment_template.attrib.get("timescale", "1"))
    except ValueError:
        timescale = 1
    try:
        presentation_time_offset = int(
            segment_template.attrib.get("presentationTimeOffset", "0")
        )
    except ValueError:
        presentation_time_offset = 0
    end_time = (
        presentation_time_offset + int(round(period_duration_seconds * timescale))
        if period_duration_seconds is not None
        else None
    )
    for index, s in enumerate(s_elements):
        duration_text = s.attrib.get("d")
        if not duration_text:
            continue
        try:
            duration = int(duration_text)
        except ValueError:
            continue

        explicit_time = s.attrib.get("t")
        if explicit_time is not None:
            try:
                current_time = int(explicit_time)
            except ValueError:
                current_time = 0 if current_time is None else current_time
        elif current_time is None:
            current_time = 0

        r_val = s.attrib.get("r")
        try:
            repeat = int(r_val) if r_val is not None else 0
        except ValueError:
            repeat = 0

        if repeat < 0:
            # A following ``t`` gives the exact end boundary. Only complete
            # segment intervals before that boundary are repetitions; the
            # following ``S`` is emitted separately below.
            next_time = None
            if index + 1 < len(s_elements):
                next_t = s_elements[index + 1].attrib.get("t")
                if next_t is not None:
                    try:
                        next_time = int(next_t)
                    except ValueError:
                        pass
            has_explicit_next_time = next_time is not None
            if next_time is None and end_time is not None:
                next_time = end_time
            if next_time is not None and next_time > current_time:
                if has_explicit_next_time:
                    segment_count = (next_time - current_time) // duration
                else:
                    segment_count = (next_time - current_time + duration - 1) // duration
                repeat = max(0, segment_count - 1)
            else:
                # Without a period duration there is no finite boundary to
                # infer. Preserve one segment rather than inventing URLs.
                repeat = 0

        total = repeat + 1
        for _ in range(total):
            result.append(seg_num)
            seg_num += 1
            current_time += duration

    return result


def get_manifest_subtitles(manifest: ET.Element) -> Dict[str, str]:
    """Extract subtitle tracks declared inside DASH MPD AdaptationSets (e.g. WebVTT)."""
    subtitles: Dict[str, str] = {}
    for adapt in manifest.iter():
        if _clean_tag(adapt.tag) != "AdaptationSet":
            continue
        mime = adapt.attrib.get("mimeType", "").lower()
        ctype = adapt.attrib.get("contentType", "").lower()
        if "text" in mime or "text" in ctype or "vtt" in mime or "sub" in mime:
            lang = adapt.attrib.get("lang") or "en-US"
            # Extract BaseURL from inside the AdaptationSet or Representation
            for elem in adapt.iter():
                if _clean_tag(elem.tag) == "BaseURL" and elem.text and elem.text.strip():
                    url = elem.text.strip()
                    if url.startswith("http://") or url.startswith("https://"):
                        subtitles[lang] = url
                        break
    return subtitles


