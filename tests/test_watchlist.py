import io
import json
import unittest
from unittest.mock import MagicMock, patch

from crunchyroll.api import (
    get_active_profile_id,
    get_active_account_id,
    get_user_profiles,
    get_user_watchlist,
    get_avatar_url,
)
from crunchyroll.auth import switch_profile
from crunchyroll import server as web_gui


class TestWatchlist(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_client.token = "header.eyJwcm9maWxlX2lkIjogInByb2YtMTIzIiwgInN1YiI6ICJhY2N0LTQ1NiJ9.signature"
        self.mock_client.etp_rt = "test-etp-rt"

    def test_get_active_profile_id_from_jwt(self):
        pid = get_active_profile_id(self.mock_client)
        self.assertEqual(pid, "prof-123")

    def test_get_active_account_id_from_jwt(self):
        aid = get_active_account_id(self.mock_client)
        self.assertEqual(aid, "acct-456")

    def test_get_active_account_id_fallback(self):
        self.mock_client.token = ""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"account_id": "acct-999"}
        self.mock_client.do_request.return_value = mock_resp

        aid = get_active_account_id(self.mock_client)
        self.assertEqual(aid, "acct-999")

    @patch("crunchyroll.auth.requests.post")
    @patch("crunchyroll.auth.save_config")
    def test_switch_profile_mints_scoped_token(self, mock_save, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "scoped-token-xyz",
            "expires_in": 300,
            "account_id": "acct-1",
            "profile_id": "prof-2",
        }
        mock_post.return_value = mock_resp

        token = switch_profile("test-rt", "prof-2")
        self.assertEqual(token, "scoped-token-xyz")
        mock_save.assert_called_with({"selected_profile_id": "prof-2"})
        # Verify grant_type was refresh_token_profile_id
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["data"]["grant_type"], "refresh_token_profile_id")
        self.assertEqual(kwargs["data"]["profile_id"], "prof-2")

    def test_get_active_profile_id_fallback_to_accounts(self):
        self.mock_client.token = ""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"account_id": "acct-789"}
        self.mock_client.do_request.return_value = mock_resp

        pid = get_active_profile_id(self.mock_client)
        self.assertEqual(pid, "acct-789")

    def test_get_user_profiles_multiprofile(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "profiles": [
                {
                    "profile_id": "prof-1",
                    "profile_name": "Main User",
                    "avatar": "avatar1.png",
                    "is_primary": True,
                    "is_selected": True,
                },
                {
                    "profile_id": "prof-2",
                    "profile_name": "Second User",
                    "avatar": "avatar2.png",
                    "is_primary": False,
                    "is_selected": False,
                },
            ]
        }
        self.mock_client.do_request.return_value = mock_resp

        profiles = get_user_profiles(self.mock_client)
        self.assertEqual(len(profiles), 2)
        self.assertEqual(profiles[0]["name"], "Main User")
        self.assertEqual(profiles[0]["avatar_url"], "https://static.crunchyroll.com/assets/avatar/170x170/avatar1.png")
        self.assertTrue(profiles[0]["is_primary"])
        self.assertTrue(profiles[0]["is_selected"])
        self.assertEqual(profiles[1]["name"], "Second User")
        self.assertEqual(profiles[1]["avatar_url"], "https://static.crunchyroll.com/assets/avatar/170x170/avatar2.png")

    def test_get_avatar_url_resolution(self):
        # File with extension
        self.assertEqual(
            get_avatar_url("psycopassv1.png"),
            "https://static.crunchyroll.com/assets/avatar/170x170/psycopassv1.png",
        )
        # Profile type fallback without extension
        self.assertEqual(
            get_avatar_url("", "aggretsuko"),
            "https://static.crunchyroll.com/assets/avatar/170x170/aggretsuko.png",
        )
        # Empty fallback to default
        self.assertEqual(
            get_avatar_url(""),
            "https://static.crunchyroll.com/assets/avatar/170x170/0001-cr-white-orange.png",
        )

    def test_get_user_profiles_fallback_single(self):
        # 404 on multiprofile, 200 on /accounts/v1/me
        resp_404 = MagicMock(status_code=404)
        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = {
            "account_id": "single-acct-1",
            "username": "SoloUser",
            "avatar": "solo.png",
        }
        self.mock_client.do_request.side_effect = [resp_404, resp_200]

        profiles = get_user_profiles(self.mock_client)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["profile_id"], "single-acct-1")
        self.assertEqual(profiles[0]["name"], "SoloUser")

    def test_get_user_profiles_unauthenticated(self):
        client = MagicMock()
        client.token = ""
        client.etp_rt = ""
        with self.assertRaises(RuntimeError):
            get_user_profiles(client)

    def test_get_user_watchlist_parsing_and_deduplication(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "total": 3,
            "data": [
                {
                    "is_favorite": True,
                    "panel": {
                        "type": "series",
                        "id": "SERIES-1",
                        "title": "Chainsaw Man",
                        "description": "Devils and hunters",
                        "images": {
                            "poster_tall": [
                                [
                                    {"width": 300, "height": 450, "source": "https://img/poster1.jpg"}
                                ]
                            ]
                        },
                    },
                },
                {
                    # Duplicate series entry (e.g. recent episode of SERIES-1)
                    "is_favorite": False,
                    "panel": {
                        "type": "episode",
                        "id": "EP-99",
                        "title": "Episode 2",
                        "episode_metadata": {
                            "series_id": "SERIES-1",
                            "series_title": "Chainsaw Man",
                        },
                    },
                },
                {
                    # Movie entry
                    "is_favorite": False,
                    "panel": {
                        "type": "movie_listing",
                        "id": "MOVIE-2",
                        "title": "Demon Slayer Movie",
                        "description": "Mugen Train",
                        "images": {
                            "thumbnail": [
                                [
                                    {"width": 640, "height": 360, "source": "https://img/thumb2.jpg"}
                                ]
                            ]
                        },
                    },
                },
            ],
        }
        self.mock_client.do_request.return_value = mock_resp

        items = get_user_watchlist(self.mock_client, profile_id="prof-123")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], "SERIES-1")
        self.assertEqual(items[0]["title"], "Chainsaw Man")
        self.assertEqual(items[0]["poster_url"], "https://img/poster1.jpg")
        self.assertTrue(items[0]["is_favorite"])
        self.assertEqual(items[0]["type"], "series")

        self.assertEqual(items[1]["id"], "MOVIE-2")
        self.assertEqual(items[1]["title"], "Demon Slayer Movie")
        self.assertEqual(items[1]["poster_url"], "https://img/thumb2.jpg")
        self.assertEqual(items[1]["type"], "movie")

    def test_get_user_watchlist_status_attributes(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "total": 1,
            "data": [
                {
                    "is_favorite": True,
                    "fully_watched": True,
                    "never_watched": False,
                    "playhead": 1420,
                    "new": True,
                    "panel": {
                        "type": "episode",
                        "id": "EP-1",
                        "title": "Ep 1",
                        "episode_metadata": {
                            "series_id": "SERIES-XYZ",
                            "series_title": "Cool Anime",
                            "duration_ms": 1420000,
                            "upload_date": "2025-01-01T00:00:00Z",
                        },
                    },
                }
            ],
        }
        self.mock_client.do_request.return_value = mock_resp

        items = get_user_watchlist(self.mock_client, profile_id="prof-123")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertTrue(item["is_favorite"])
        self.assertTrue(item["fully_watched"])
        self.assertFalse(item["never_watched"])
        self.assertEqual(item["playhead"], 1420)
        self.assertTrue(item["is_new"])
        self.assertEqual(item["upload_date"], "2025-01-01T00:00:00Z")
        self.assertEqual(item["duration_ms"], 1420000)
        self.assertEqual(item["next_episode_title"], "Ep 1")

    def test_server_do_get_parse_qs_scope(self):
        handler = web_gui.Handler.__new__(web_gui.Handler)
        handler.path = "/api/stars"
        handler._validate_origin = MagicMock(return_value=True)
        response_data = {}
        handler._json = lambda data, code=200: response_data.update({"code": code, "body": data})

        with patch("crunchyroll.server.get_github_stars", return_value=123):
            # This must NOT raise UnboundLocalError: cannot access local variable 'parse_qs'
            handler.do_GET()

        self.assertEqual(response_data.get("code"), 200)
        self.assertEqual(response_data.get("body", {}).get("stars"), 123)

    @patch("crunchyroll.auth.switch_profile", return_value="new-tok-123")
    def test_server_profiles_switch_post(self, mock_switch):
        handler = web_gui.Handler.__new__(web_gui.Handler)
        handler.path = "/api/profiles/switch"
        handler._validate_origin = MagicMock(return_value=True)

        payload = json.dumps({"profile_id": "prof-target"}).encode("utf-8")
        handler.headers = {"Content-Length": str(len(payload))}
        handler.rfile = io.BytesIO(payload)

        response_data = {}
        handler._json = lambda data, code=200: response_data.update({"code": code, "body": data})

        with patch.dict(web_gui.STATE, {"etp_rt": "valid-etp-rt", "config": {}}):
            handler.do_POST()

        self.assertEqual(response_data.get("code"), 200)
        self.assertTrue(response_data.get("body", {}).get("success"))
        self.assertEqual(response_data.get("body", {}).get("active_profile_id"), "prof-target")
        mock_switch.assert_called_with("valid-etp-rt", "prof-target")

    @patch("crunchyroll.auth.switch_profile", return_value="new-tok-pin")
    def test_server_profiles_switch_with_pin(self, mock_switch):
        handler = web_gui.Handler.__new__(web_gui.Handler)
        handler.path = "/api/profiles/switch"
        handler._validate_origin = MagicMock(return_value=True)

        payload = json.dumps({"profile_id": "prof-locked", "pin": "6620"}).encode("utf-8")
        handler.headers = {"Content-Length": str(len(payload))}
        handler.rfile = io.BytesIO(payload)

        response_data = {}
        handler._json = lambda data, code=200: response_data.update({"code": code, "body": data})

        with patch.dict(web_gui.STATE, {"etp_rt": "valid-etp-rt", "config": {}}):
            handler.do_POST()

        self.assertEqual(response_data.get("code"), 200)
        self.assertTrue(response_data.get("body", {}).get("success"))
        mock_switch.assert_called_with("valid-etp-rt", "prof-locked", pin="6620")

    @patch("crunchyroll.auth.switch_profile", side_effect=PermissionError("PIN_REQUIRED"))
    def test_server_profiles_switch_requires_pin(self, mock_switch):
        handler = web_gui.Handler.__new__(web_gui.Handler)
        handler.path = "/api/profiles/switch"
        handler._validate_origin = MagicMock(return_value=True)

        payload = json.dumps({"profile_id": "prof-locked"}).encode("utf-8")
        handler.headers = {"Content-Length": str(len(payload))}
        handler.rfile = io.BytesIO(payload)

        response_data = {}
        handler._json = lambda data, code=200: response_data.update({"code": code, "body": data})

        with patch.dict(web_gui.STATE, {"etp_rt": "valid-etp-rt", "config": {}}):
            handler.do_POST()

        self.assertEqual(response_data.get("code"), 400)
        self.assertFalse(response_data.get("body", {}).get("success"))
        self.assertTrue(response_data.get("body", {}).get("requires_pin"))

    @patch("crunchyroll.auth.requests.post")
    def test_validate_profile_pin(self, mock_post):
        from crunchyroll.auth import validate_profile_pin

        # Successful PIN check
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"code": "pass-token-xyz"})
        code = validate_profile_pin("acc-123", "prof-456", "6620", "bearer-token")
        self.assertEqual(code, "pass-token-xyz")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"], {
            "credential_type": "profile_pin",
            "profile_id": "prof-456",
            "value": "6620",
        })

        # Incorrect PIN check (401)
        mock_post.reset_mock()
        mock_post.return_value = MagicMock(status_code=401, text="invalid pin")
        with self.assertRaises(ValueError) as ctx:
            validate_profile_pin("acc-123", "prof-456", "0000", "bearer-token")
        self.assertIn("Invalid profile PIN", str(ctx.exception))

    @patch("crunchyroll.auth.switch_profile", return_value="new-tok-pin")
    def test_server_profiles_switch_with_remember_pin(self, mock_switch):
        handler = web_gui.Handler.__new__(web_gui.Handler)
        handler.path = "/api/profiles/switch"
        handler._validate_origin = MagicMock(return_value=True)

        payload = json.dumps({"profile_id": "prof-locked", "pin": "6620", "remember_pin": True}).encode("utf-8")
        handler.headers = {"Content-Length": str(len(payload))}
        handler.rfile = io.BytesIO(payload)

        response_data = {}
        handler._json = lambda data, code=200: response_data.update({"code": code, "body": data})

        with patch.dict(web_gui.STATE, {"etp_rt": "valid-etp-rt", "config": {}}):
            handler.do_POST()

        self.assertEqual(response_data.get("code"), 200)
        self.assertTrue(response_data.get("body", {}).get("success"))
        mock_switch.assert_called_with("valid-etp-rt", "prof-locked", pin="6620", remember_pin=True)

    @patch("crunchyroll.auth.get_access_token", return_value="mock-tok")
    @patch("crunchyroll.auth.validate_profile_pin")
    @patch("crunchyroll.auth.load_config")
    @patch("crunchyroll.auth.save_config")
    def test_switch_profile_remember_and_purge(self, mock_save_config, mock_load_config, mock_val_pin, mock_get_acc):
        from crunchyroll.auth import switch_profile

        # Case 1: Remember PIN
        mock_load_config.return_value = {"saved_profile_pins": {}}
        mock_val_pin.return_value = "pass-token-123"
        switch_profile("etp-rt-1", "prof-1", pin="6620", account_id="acc-1", remember_pin=True)
        mock_save_config.assert_called_with({
            "selected_profile_id": "prof-1",
            "saved_profile_pins": {"prof-1": "6620"},
        })

        # Case 2: Stale saved PIN triggers ValueError and purges saved pin
        mock_load_config.return_value = {"saved_profile_pins": {"prof-1": "stale-pin"}}
        mock_val_pin.side_effect = ValueError("Invalid profile PIN")
        with self.assertRaises(ValueError):
            switch_profile("etp-rt-1", "prof-1", account_id="acc-1")
        # Ensure it was purged
        mock_save_config.assert_called_with({"saved_profile_pins": {}})


if __name__ == "__main__":
    unittest.main()
