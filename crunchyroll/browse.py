"""
Module to obtain animes on broadcast (Browse API).

This API returns the most recently added, popular, etc. animes.
URL: https://www.crunchyroll.com/content/v2/discover/browse
"""

from typing import Dict, Any, List, Optional
import requests

from .http_client import CrunchyrollHttpClient

def get_browse_anime(
    client: CrunchyrollHttpClient,
    limit: int = None,
    sort_by: str = None,
    ratings: bool = None,
    locale: str = None,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Retrieve anime entries from the Browse API.

    Args:
        client: CrunchyrollHttpClient instance with authenticated token.
        limit: Maximum number of results (default: 36).
        sort_by: Sorting (newly_added, popular, etc.) (default: newly_added).
        ratings: Include only animes with a rating (default: True).
        debug: If True, print details of the response to the console.

    Returns:
        Dictionary with the JSON response data.
    """
    # Use default values if not provided
    if limit is None:
        limit = 36
    if sort_by is None:
        sort_by ="newly_added"
    if ratings is None:
        ratings = True
    if locale is None:
        locale = "en-US"

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
