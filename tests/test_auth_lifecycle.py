import base64
import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from crunchyroll.auth import (
    is_jwt_expired,
    load_config,
    save_config,
)
from crunchyroll.http_client import CrunchyrollHttpClient


def _make_mock_jwt(exp_timestamp: float) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp_timestamp}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.signature"


class TestAuthLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "config.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_config_purges_keys_on_none(self):
        """save_config atomically removes keys passed with value None."""
        save_config(
            {
                "etp_rt": "token123",
                "android_access_token": "acc123",
                "android_refresh_token": "ref123",
                "username": "user1",
            },
            config_path=self.config_path,
        )
        cfg = load_config(self.config_path)
        self.assertEqual(cfg.get("etp_rt"), "token123")
        self.assertEqual(cfg.get("android_access_token"), "acc123")

        # Purge Android tokens
        save_config(
            {
                "etp_rt": "new_token",
                "android_access_token": None,
                "android_refresh_token": None,
                "username": None,
            },
            config_path=self.config_path,
        )
        cfg = load_config(self.config_path)
        self.assertEqual(cfg.get("etp_rt"), "new_token")
        self.assertNotIn("android_access_token", cfg)
        self.assertNotIn("android_refresh_token", cfg)
        self.assertNotIn("username", cfg)

    def test_is_jwt_expired(self):
        """is_jwt_expired accurately detects expiration with buffer."""
        past = time.time() - 100
        future = time.time() + 1000
        near_future = time.time() + 30  # within default 60s buffer

        self.assertTrue(is_jwt_expired(_make_mock_jwt(past)))
        self.assertTrue(is_jwt_expired(_make_mock_jwt(near_future)))
        self.assertFalse(is_jwt_expired(_make_mock_jwt(future)))
        self.assertFalse(is_jwt_expired("mock_non_jwt_string"))
        self.assertTrue(is_jwt_expired(""))
        self.assertTrue(is_jwt_expired(None))

    @patch("crunchyroll.http_client.get_access_token")
    @patch("crunchyroll.http_client.load_config")
    def test_http_client_prioritizes_explicit_etp_rt(self, mock_load_config, mock_get_access_token):
        """Explicit etp_rt passed to constructor overrides stale Android tokens in config."""
        mock_load_config.return_value = {
            "android_access_token": "stale_android_token",
            "android_refresh_token": "stale_android_ref",
        }
        mock_get_access_token.return_value = "fresh_web_access_token"

        client = CrunchyrollHttpClient(etp_rt="user_provided_etp_rt")
        self.assertEqual(client.token, "fresh_web_access_token")
        mock_get_access_token.assert_called_with("user_provided_etp_rt")

    @patch("crunchyroll.auth.refresh_android_tv_token")
    @patch("crunchyroll.http_client.load_config")
    def test_http_client_proactively_refreshes_expired_android_token(
        self, mock_load_config, mock_refresh_android
    ):
        """On init, an expired Android JWT token is proactively refreshed via refresh token."""
        expired_token = _make_mock_jwt(time.time() - 3600)
        mock_load_config.return_value = {
            "android_access_token": expired_token,
            "android_refresh_token": "valid_refresh_token",
        }
        mock_refresh_android.return_value = ("brand_new_access_token", "brand_new_refresh_token")

        client = CrunchyrollHttpClient()
        self.assertEqual(client.token, "brand_new_access_token")
        mock_refresh_android.assert_called_once_with("valid_refresh_token")

    @patch("crunchyroll.auth.refresh_android_tv_token")
    @patch("crunchyroll.http_client.get_access_token")
    @patch("crunchyroll.http_client.load_config")
    def test_http_client_falls_back_to_etp_rt_on_dead_android_refresh(
        self, mock_load_config, mock_get_access_token, mock_refresh_android
    ):
        """When Android TV token refresh fails, stale credentials are discarded and etp_rt is used."""
        expired_token = _make_mock_jwt(time.time() - 3600)
        mock_load_config.return_value = {
            "android_access_token": expired_token,
            "android_refresh_token": "dead_refresh_token",
            "etp_rt": "saved_etp_rt_token",
        }
        mock_refresh_android.side_effect = RuntimeError("Refresh token revoked or expired")
        mock_get_access_token.return_value = "fallback_web_token"

        client = CrunchyrollHttpClient()
        self.assertEqual(client.token, "fallback_web_token")
        self.assertEqual(client.android_token, "")
        self.assertEqual(client.android_refresh_token, "")
        mock_get_access_token.assert_called_with("saved_etp_rt_token")

    @patch("crunchyroll.auth.refresh_android_tv_token")
    def test_do_request_refreshes_and_retries_on_http_403(self, mock_refresh_android):
        """do_request catches HTTP 403 Forbidden, refreshes token, updates Authorization header and retries."""
        mock_refresh_android.return_value = ("refreshed_access_token_456", "refreshed_refresh_token")

        client = CrunchyrollHttpClient()
        client.token = "initial_expired_token"
        client.android_token = "initial_expired_token"
        client.android_refresh_token = "valid_refresh_token"

        resp_403 = MagicMock()
        resp_403.status_code = 403
        resp_403.text = "Forbidden"

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.text = '{"success": true}'

        # First attempt returns 403, retry returns 200
        client.session.request = MagicMock(side_effect=[resp_403, resp_200])

        url = "https://cr-play-service.prd.crunchyrollsvc.com/v3/G69P9MD9Y/tv/android_tv/play?queue=0"
        headers = {"Authorization": "Bearer initial_expired_token"}

        final_resp = client.do_request("GET", url, headers=headers)
        self.assertEqual(final_resp.status_code, 200)

        # Verify second call received refreshed token in Authorization header
        self.assertEqual(client.session.request.call_count, 2)
        second_call_headers = client.session.request.call_args_list[1][1]["headers"]
        self.assertEqual(second_call_headers["Authorization"], "Bearer refreshed_access_token_456")


    @patch("crunchyroll.auth.get_guest_token")
    def test_search_series_falls_back_to_guest_token_on_auth_failure(self, mock_get_guest_token):
        """search_series falls back to guest token if user token fails with 401 or 403."""
        from crunchyroll.api import search_series

        mock_get_guest_token.return_value = "guest_token_xyz"

        client = MagicMock()
        client.token = "expired_user_token"

        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_401.text = '{"code":"content.error.auth_error","context":[]}'

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "data": [
                {
                    "items": [
                        {
                            "id": "GR12345",
                            "type": "series",
                            "title": "Black Clover",
                            "series_metadata": {"season_count": 4, "episode_count": 170},
                        }
                    ]
                }
            ]
        }

        # client.do_request returns 401 on initial queries, then 200 with guest headers
        client.do_request = MagicMock(side_effect=[resp_401, resp_401, resp_200])

        results = search_series(client, "black clover")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "GR12345")
        self.assertEqual(results[0]["title"], "Black Clover")
        mock_get_guest_token.assert_called_once()


if __name__ == "__main__":
    unittest.main()
