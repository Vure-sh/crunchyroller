import unittest
from unittest.mock import patch, MagicMock
import io
import json

from crunchyroll.version import get_github_stars, _STARS_CACHE


class TestStars(unittest.TestCase):
    def setUp(self):
        _STARS_CACHE["checked_at"] = 0.0
        _STARS_CACHE["stars"] = None

    @patch("urllib.request.urlopen")
    def test_get_github_stars_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"stargazers_count": 42}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        stars = get_github_stars(force=True)
        self.assertEqual(stars, 42)

    @patch("urllib.request.urlopen")
    def test_get_github_stars_cached(self, mock_urlopen):
        _STARS_CACHE["checked_at"] = 9999999999.0
        _STARS_CACHE["stars"] = 55

        stars = get_github_stars(force=False)
        self.assertEqual(stars, 55)
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_get_github_stars_failure_fallback(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Network offline")
        stars = get_github_stars(force=True)
        self.assertEqual(stars, 0)


if __name__ == "__main__":
    unittest.main()
