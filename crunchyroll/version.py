"""crunchyroll/version.py — GitHub release update checking and semver parsing."""

import json
import logging
import re
import time
import urllib.request
from typing import Any, Dict, Optional, Tuple

from crunchyroll import __version__

logger = logging.getLogger("crunchyroller.version")

_VERSION_CACHE: Dict[str, Any] = {
    "checked_at": 0.0,
    "data": None,
}

GITHUB_REPO = "Vure-sh/crunchyroller"
CACHE_DURATION_SEC = 3600  # 1 hour


def parse_semver(v_str: str) -> Tuple[int, ...]:
    """Extracts integer tuple from version string like 'v3.4.0' -> (3, 4, 0)."""
    raw = str(v_str).strip()
    core = raw.split("-")[0].split("+")[0]
    clean = re.sub(r"^[^\d]*", "", core)
    parts = []
    for piece in clean.split("."):
        m = re.match(r"^(\d+)", piece)
        if m:
            parts.append(int(m.group(1)))
        else:
            break
    return tuple(parts) if parts else (0,)


def check_for_updates(
    force: bool = False,
    timeout: float = 3.5,
    custom_repo: Optional[str] = None,
) -> Dict[str, Any]:
    """Queries GitHub Releases API with in-memory caching to check if a new version is available."""
    global _VERSION_CACHE
    now = time.time()
    if not force and _VERSION_CACHE["data"] is not None and (now - _VERSION_CACHE["checked_at"] < CACHE_DURATION_SEC):
        return _VERSION_CACHE["data"]

    current_ver = __version__
    repo = custom_repo or GITHUB_REPO
    url = f"https://api.github.com/repos/{repo}/releases/latest"

    result: Dict[str, Any] = {
        "current_version": current_ver,
        "latest_version": current_ver,
        "has_update": False,
        "release_url": f"https://github.com/{repo}/releases/latest",
        "release_name": "",
        "published_at": "",
    }

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"crunchyroller/{current_ver}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                payload = json.loads(resp.read().decode("utf-8"))
                tag_name = payload.get("tag_name", "")
                html_url = payload.get("html_url", result["release_url"])
                rel_name = payload.get("name", tag_name)
                pub_at = payload.get("published_at", "")

                remote_tuple = parse_semver(tag_name)
                local_tuple = parse_semver(current_ver)

                has_update = remote_tuple > local_tuple

                result.update({
                    "latest_version": tag_name.lstrip("v"),
                    "has_update": has_update,
                    "release_url": html_url,
                    "release_name": rel_name,
                    "published_at": pub_at,
                })
    except Exception as e:
        logger.debug("Check for updates failed: %s", e)

    _VERSION_CACHE["checked_at"] = now
    _VERSION_CACHE["data"] = result
    return result
