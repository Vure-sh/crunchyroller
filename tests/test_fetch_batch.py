import io
import json
import unittest
from unittest.mock import MagicMock, patch

from crunchyroll import server as web_gui


class TestFetchBatch(unittest.TestCase):
    def test_multi_url_fetch_post(self):
        """Test concurrent multi-anime metadata fetching through /api/fetch."""
        mock_series_1 = {
            "title": "Jujutsu Kaisen",
            "description": "Cursed energy anime",
            "poster": "https://img.cr.com/jjk.jpg",
            "seasons": [
                MagicMock(id="sn-1", season_number=1, title="Season 1", audio_locale="ja-JP")
            ],
            "episodes": [
                MagicMock(id="ep-1", title="Ep 1", episode_number=1, season_number=1, series_title="Jujutsu Kaisen", season_id="sn-1")
            ],
        }
        mock_series_2 = {
            "title": "Chainsaw Man",
            "description": "Devils and hunters",
            "poster": "https://img.cr.com/csm.jpg",
            "seasons": [
                MagicMock(id="sn-2", season_number=1, title="Season 1", audio_locale="ja-JP")
            ],
            "episodes": [
                MagicMock(id="ep-2", title="Ep 1", episode_number=1, season_number=1, series_title="Chainsaw Man", season_id="sn-2")
            ],
        }

        def mock_get_series(client, cid, al, sl):
            if "G69V5WVM6" in cid:
                return mock_series_1
            return mock_series_2

        with patch("crunchyroll.server.CrunchyrollHttpClient"), \
             patch("crunchyroll.server.get_series", side_effect=mock_get_series):

            handler = web_gui.Handler.__new__(web_gui.Handler)
            handler.path = "/api/fetch"
            raw_payload = json.dumps({
                "urls": [
                    "https://www.crunchyroll.com/series/G69V5WVM6/jujutsu-kaisen",
                    "https://www.crunchyroll.com/series/GVDHX8QNW/chainsaw-man",
                ]
            }).encode("utf-8")
            handler.headers = {"Content-Length": str(len(raw_payload))}
            handler.rfile = io.BytesIO(raw_payload)

            response_data = {}
            def fake_json(data, code=200):
                response_data["code"] = code
                response_data["body"] = data

            handler._json = fake_json
            handler.do_POST()

            self.assertEqual(response_data.get("code"), 200)
            body = response_data.get("body", {})
            self.assertTrue(body.get("success"))
            self.assertEqual(body.get("count"), 2)
            self.assertEqual(len(body.get("animes", [])), 2)
            titles = [a["title"] for a in body["animes"]]
            self.assertIn("Jujutsu Kaisen", titles)
            self.assertIn("Chainsaw Man", titles)
            print(f"\n[Verify Batch Fetch] Fetched titles: {titles}")

    def test_multi_anime_download_post(self):
        """Test /api/download groups multi-anime items into separate tasks."""
        handler = web_gui.Handler.__new__(web_gui.Handler)
        handler.path = "/api/download"
        raw_payload = json.dumps({
            "items": [
                {"id": "ep-1", "title": "Ep 1", "series_title": "Attack on Titan"},
                {"id": "ep-2", "title": "Ep 2", "series_title": "Attack on Titan"},
                {"id": "ep-3", "title": "Ep 1", "series_title": "Frieren"},
            ]
        }).encode("utf-8")
        handler.headers = {"Content-Length": str(len(raw_payload))}
        handler.rfile = io.BytesIO(raw_payload)

        response_data = {}
        def fake_json(data, code=200):
            response_data["code"] = code
            response_data["body"] = data

        handler._json = fake_json

        mock_queue = MagicMock()
        mock_queue.enqueue_batch.side_effect = lambda items, opts, task_title: [MagicMock() for _ in items]
        mock_queue.queued_count = 3

        with patch("crunchyroll.server.is_authenticated", return_value=True), \
             patch("crunchyroll.server.QUEUE", mock_queue):
            handler.do_POST()

        self.assertEqual(response_data.get("code"), 200)
        body = response_data.get("body", {})
        self.assertTrue(body.get("success"))
        self.assertEqual(body.get("enqueued_count"), 3)
        self.assertEqual(mock_queue.enqueue_batch.call_count, 2)
        called_titles = [call.kwargs.get("task_title") for call in mock_queue.enqueue_batch.call_args_list]
        self.assertIn("Attack on Titan", called_titles)
        self.assertIn("Frieren", called_titles)
        print(f"\n[Verify Batch Download] Grouped tasks created: {called_titles}")


if __name__ == "__main__":
    unittest.main()
