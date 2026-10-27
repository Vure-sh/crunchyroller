import time
from unittest.mock import MagicMock
from crunchyroll.browse import get_browse_anime, clear_browse_cache, DEFAULT_BROWSE_CACHE_TTL


def test_browse_anime_caching():
    clear_browse_cache()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "total": 2,
        "data": [
            {"id": "G1", "title": "Anime 1"},
            {"id": "G2", "title": "Anime 2"},
        ],
    }
    mock_client.do_request.return_value = mock_response

    # First call: hits network
    res1 = get_browse_anime(mock_client, limit=36, sort_by="newly_added", locale="en-US")
    assert res1["total"] == 2
    assert mock_client.do_request.call_count == 1

    # Second call with same params: uses cache, no network hit
    res2 = get_browse_anime(mock_client, limit=36, sort_by="newly_added", locale="en-US")
    assert res2["total"] == 2
    assert mock_client.do_request.call_count == 1

    # Force refresh: hits network again
    res3 = get_browse_anime(mock_client, limit=36, sort_by="newly_added", locale="en-US", force_refresh=True)
    assert res3["total"] == 2
    assert mock_client.do_request.call_count == 2

    # Clear cache and verify next call hits network
    clear_browse_cache()
    res4 = get_browse_anime(mock_client, limit=36, sort_by="newly_added", locale="en-US")
    assert res4["total"] == 2
    assert mock_client.do_request.call_count == 3
