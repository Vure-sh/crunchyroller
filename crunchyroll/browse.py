"""
Module to obtain animes on broadcast (Browse API).

This API returns the most recently added, popular, etc. animes.
URL: https://www.crunchyroll.com/content/v2/discover/browse
"""

from typing import Dict, Any, List, Optional, Tuple
import copy
import threading
import time
import requests

from .http_client import CrunchyrollHttpClient

_BROWSE_CACHE: Dict[Tuple[str, int, bool, str], Tuple[Dict[str, Any], float]] = {}
_BROWSE_CACHE_LOCK = threading.Lock()
DEFAULT_BROWSE_CACHE_TTL = 600.0  # 10 minutes cache


def clear_browse_cache() -> None:
    """Clear all cached Browse API responses."""
    with _BROWSE_CACHE_LOCK:
        _BROWSE_CACHE.clear()


def get_browse_anime(
    client: CrunchyrollHttpClient,
    limit: int = None,
    sort_by: str = None,
    ratings: bool = None,
    locale: str = None,
    debug: bool = False,
    force_refresh: bool = False,
    ttl: float = DEFAULT_BROWSE_CACHE_TTL,
) -> Dict[str, Any]:
    """
    Retrieve anime entries from the Browse API, using an in-memory cache to avoid redundant network queries.

    Args:
        client: CrunchyrollHttpClient instance with authenticated token.
        limit: Maximum number of results (default: 36).
        sort_by: Sorting (newly_added, popular, etc.) (default: newly_added).
        ratings: Include only animes with a rating (default: True).
        locale: Desired subtitle/content locale (default: en-US).
        debug: If True, print details of the response to the console.
        force_refresh: If True, bypass the cache and fetch fresh results from Crunchyroll.
        ttl: Time-to-live in seconds for cached browse responses (default: 600s / 10m).

    Returns:
        Dictionary with the JSON response data.
    """
    # Use default values if not provided
    if limit is None:
        limit = 36
    if sort_by is None:
        sort_by = "newly_added"
    if ratings is None:
        ratings = True
    if locale is None:
        locale = "en-US"

    cache_key = (str(sort_by), int(limit), bool(ratings), str(locale))
    now = time.time()

    if not force_refresh:
        with _BROWSE_CACHE_LOCK:
            if cache_key in _BROWSE_CACHE:
                cached_data, timestamp = _BROWSE_CACHE[cache_key]
                if now - timestamp < ttl:
                    if debug:
                        print(f"[browse] Returning cached results (age: {now - timestamp:.1f}s)")
                    return copy.deepcopy(cached_data)

    # Build URL
    url = f"https://www.crunchyroll.com/content/v2/discover/browse"
    params = {
        "n": limit,
        "sort_by": sort_by,
        "ratings": str(ratings).lower(),
        "locale": locale,
    }

    try:
        response = client.do_request("GET", url, params=params)
        response.raise_for_status()

        data = response.json()

        # Cache the successful response
        if isinstance(data, dict):
            with _BROWSE_CACHE_LOCK:
                _BROWSE_CACHE[cache_key] = (copy.deepcopy(data), now)
        
        if debug:
            print("\n" + "="*60)
            print("[browse] Response received:")
            print("="*60)
            print(f"Status Code: {response.status_code}")
            print(f"URL: {url}")
            print(f"Parameters: {params}")
            print(f"Data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
            print(f"Total items: {data.get('total', 'N/A')}")
            print(f"Items returned: {len(data.get('data', [])) if isinstance(data.get('data'), list) else 'N/A'}")
            print("="*60 + "\n")
            
            # Show summary of each anime
            items = data.get('data', [])
            if isinstance(items, list) and items:
                print("ANIME SUMMARY")
                print("-"*60)
                for i, item in enumerate(items[:5]):  # Show only the first 5
                    print(f"\n--- Anime {i+1} ---")
                    print(f"  ID: {item.get('id', 'N/A')}")
                    print(f"  Title: {item.get('title', 'N/A')}")
                    print(f"  Type: {item.get('type', 'N/A')}")
                    status = item.get('status', 'N/A')
                    print(f"  Status: {status}")
                    print(f"  Description: {item.get('description', 'N/A')[:150]}...")
        
        return data
        
    except requests.exceptions.HTTPError as e:
        if debug:
            print(f"\n[browse] Error HTTP: {e}")
            print(f"  Status: {e.response.status_code if e.response else 'N/A'}")
            print(f"  Response: {e.response.text[:500] if e.response else 'N/A'}")
        raise
    except requests.exceptions.RequestException as e:
        if debug:
            print(f"\n[browse] Request error: {e}")
        raise
    except Exception as e:
        if debug:
            print(f"\n[browse] Unexpected error: {type(e).__name__}: {e}")
        raise
