import io
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from crunchyroll.watcher import MonitoredStore, SeriesWatcher
from crunchyroll import server as web_gui


class TestSeriesWatcher(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store_file = os.path.join(self.temp_dir, "test_monitored.json")
        self.store = MonitoredStore(self.store_file)

        self.mock_queue = MagicMock()
        self.mock_queue.enqueue_batch.return_value = ["job-123"]
        self.mock_client = MagicMock()
        self.mock_config = {
            "audio_lang": "ja-JP",
            "subs_lang": "en-US",
            "video_quality": "1080p",
            "audio_quality": "192k",
            "download_dir": "anime",
            "workers": 16,
        }

        self.watcher = SeriesWatcher(
            queue=self.mock_queue,
            client_factory=lambda: self.mock_client,
            config_provider=lambda: self.mock_config,
            store=self.store,
        )

    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    def test_store_initialization_and_persistence(self):
        data = self.store.load()
        self.assertTrue(data["settings"]["enabled"])
        self.assertEqual(data["settings"]["interval_minutes"], 60)
        self.assertEqual(data["series"], {})

        # Modify and save
        data["series"]["SERIES-1"] = {"id": "SERIES-1", "title": "Chainsaw Man"}
        self.store.save(data)

        reloaded = self.store.load()
        self.assertIn("SERIES-1", reloaded["series"])
        self.assertEqual(reloaded["series"]["SERIES-1"]["title"], "Chainsaw Man")

    @patch("crunchyroll.api.get_series")
    def test_add_series_latest_only_prepopulates_episodes(self, mock_get_series):
        ep1 = MagicMock(id="EP-1", episode_number=1, season_number=1, title="Ep 1")
        ep2 = MagicMock(id="EP-2", episode_number=2, season_number=1, title="Ep 2")
        mock_get_series.return_value = {"episodes": [ep1, ep2]}

        rec = self.watcher.add_series("SERIES-A", "Cool Anime", mode="latest_only")
        self.assertEqual(rec["id"], "SERIES-A")
        self.assertEqual(rec["mode"], "latest_only")
        self.assertEqual(set(rec["known_episodes"]), {"EP-1", "EP-2"})

        # Subsequent check with no new episodes should enqueue 0
        mock_get_series.return_value = {"episodes": [ep1, ep2]}
        res = self.watcher.check_series("SERIES-A")
        self.assertEqual(res["new_episodes"], 0)
        self.mock_queue.enqueue_batch.assert_not_called()

    @patch("crunchyroll.api.get_series")
    def test_detect_new_episode_and_enqueue(self, mock_get_series):
        ep1 = MagicMock(id="EP-1", episode_number=1, season_number=1, title="Ep 1", season_title="S1")
        ep2 = MagicMock(id="EP-2", episode_number=2, season_number=1, title="Ep 2", season_title="S1")
        mock_get_series.return_value = {"episodes": [ep1]}

        self.watcher.add_series("SERIES-A", "Cool Anime", mode="latest_only")

        # Now simulate episode 2 drops!
        mock_get_series.return_value = {"episodes": [ep1, ep2]}
        res = self.watcher.check_series("SERIES-A")

        self.assertEqual(res["new_episodes"], 1)
        self.mock_queue.enqueue_batch.assert_called_once()
        args, kwargs = self.mock_queue.enqueue_batch.call_args
        items = args[0]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "EP-2")
        self.assertEqual(items[0]["title"], "Ep 2")

        # Verify series record is updated with EP-2 in downloaded_episodes
        status = self.watcher.get_status()
        s_rec = next(s for s in status["series"] if s["id"] == "SERIES-A")
        self.assertIn("EP-2", s_rec["downloaded_episodes"])
        self.assertEqual(s_rec["last_episode_name"], "Ep 2")

    @patch("crunchyroll.api.get_series")
    def test_check_series_all_missing_mode(self, mock_get_series):
        ep1 = MagicMock(id="EP-1", episode_number=1, season_number=1, title="Ep 1", season_title="S1")
        ep2 = MagicMock(id="EP-2", episode_number=2, season_number=1, title="Ep 2", season_title="S1")
        mock_get_series.return_value = {"episodes": [ep1, ep2]}

        self.watcher.add_series("SERIES-B", "Backlog Anime", mode="all_missing")

        res = self.watcher.check_series("SERIES-B")
        self.assertEqual(res["new_episodes"], 1)  # queue mock returns 1 job
        self.mock_queue.enqueue_batch.assert_called_once()
        args, _ = self.mock_queue.enqueue_batch.call_args
        self.assertEqual(len(args[0]), 2)  # both ep 1 and ep 2 enqueued

    @patch("crunchyroll.api.get_series")
    def test_simulate_release_rollback(self, mock_get_series):
        ep1 = MagicMock(id="EP-1", episode_number=1, season_number=1, title="Ep 1", season_title="S1")
        ep2 = MagicMock(id="EP-2", episode_number=2, season_number=1, title="Ep 2", season_title="S1")
        mock_get_series.return_value = {"episodes": [ep1, ep2]}

        self.watcher.add_series("SERIES-C", "Testing Anime", mode="latest_only")

        # Ep 2 was in known_episodes. Now simulate release!
        res = self.watcher.simulate_release("SERIES-C")
        self.assertTrue(res["success"])
        self.assertEqual(res["new_episodes"], 1)
        self.mock_queue.enqueue_batch.assert_called_once()
        args, _ = self.mock_queue.enqueue_batch.call_args
        self.assertEqual(args[0][0]["id"], "EP-2")

    @patch("crunchyroll.api.get_series")
    def test_add_series_with_url_and_metadata_fetch(self, mock_get_series):
        mock_get_series.return_value = {
            "id": "GVDHX8QNW",
            "title": "Solo Leveling",
            "poster": "https://img.crunchyroll.com/poster.jpg",
            "episodes": [],
        }
        rec = self.watcher.add_series("https://www.crunchyroll.com/series/GVDHX8QNW/solo-leveling", mode="latest_only")
        self.assertEqual(rec["id"], "GVDHX8QNW")
        self.assertEqual(rec["title"], "Solo Leveling")
        self.assertEqual(rec["poster"], "https://img.crunchyroll.com/poster.jpg")
        self.assertEqual(rec["url"], "https://www.crunchyroll.com/series/GVDHX8QNW")

    def test_remove_and_toggle_series(self):
        self.watcher.add_series("SERIES-D", "Toggle Me")
        st = self.watcher.toggle_series("SERIES-D")
        self.assertEqual(st, "paused")
        st2 = self.watcher.toggle_series("SERIES-D")
        self.assertEqual(st2, "active")

        removed = self.watcher.remove_series("SERIES-D")
        self.assertTrue(removed)
        self.assertEqual(len(self.watcher.get_status()["series"]), 0)

    def test_update_settings(self):
        self.watcher._wake_event.clear()
        res = self.watcher.update_settings({"enabled": False, "interval_minutes": 15, "default_mode": "all_missing"})
        self.assertFalse(res["enabled"])
        self.assertEqual(res["interval_minutes"], 15.0)
        self.assertEqual(res["default_mode"], "all_missing")
        # Interval changed from 60 to 15, so _wake_event must be set to notify the sleeping thread
        self.assertTrue(self.watcher._wake_event.is_set())

        # If updated with same interval and enabled unchanged, _wake_event should not be re-set
        self.watcher._wake_event.clear()
        self.watcher.update_settings({"interval_minutes": 15})
        self.assertFalse(self.watcher._wake_event.is_set())

        # If enabled is flipped from False back to True, _wake_event must be set
        self.watcher.update_settings({"enabled": True})
        self.assertTrue(self.watcher._wake_event.is_set())

    def test_server_watcher_api_endpoints(self):
        handler = web_gui.Handler.__new__(web_gui.Handler)
        handler._validate_origin = MagicMock(return_value=True)

        # GET /api/watcher/status
        handler.path = "/api/watcher/status"
        resp = {}
        handler._json = lambda data, code=200: resp.update({"code": code, "body": data})
        handler.do_GET()
        self.assertEqual(resp.get("code"), 200)
        self.assertTrue(resp.get("body", {}).get("success"))
        self.assertIn("series", resp.get("body", {}))

        # POST /api/watcher/monitor
        handler.path = "/api/watcher/monitor"
        payload = json.dumps({"series_id": "SERIES-API", "title": "API Anime", "mode": "latest_only"}).encode("utf-8")
        handler.headers = {"Content-Length": str(len(payload))}
        handler.rfile = io.BytesIO(payload)
        resp = {}
        with patch.object(web_gui.WATCHER, "add_series", return_value={"id": "SERIES-API", "title": "API Anime"}):
            handler.do_POST()
        self.assertEqual(resp.get("code"), 200)
        self.assertTrue(resp.get("body", {}).get("success"))

        # POST /api/watcher/check-now
        handler.path = "/api/watcher/check-now"
        handler.headers = {"Content-Length": "2"}
        handler.rfile = io.BytesIO(b"{}")
        resp = {}
        with patch.object(web_gui.WATCHER, "check_now") as mock_check:
            handler.do_POST()
        mock_check.assert_called_once()
        self.assertTrue(resp.get("body", {}).get("success"))



    @patch("crunchyroll.api.get_series")
    def test_all_missing_mode_detects_deleted_file_on_disk(self, mock_get_series):
        # Setup real directory structure in temp dir
        dl_dir = os.path.join(self.temp_dir, "anime")
        season_dir = os.path.join(dl_dir, "Chainsaw Man", "Season 01")
        os.makedirs(season_dir, exist_ok=True)

        # Create Episode 2 on disk (size > 1MB)
        ep2_file = os.path.join(season_dir, "Chainsaw Man - S01E02 - ARRIVAL IN TOKYO [1080p].mkv")
        with open(ep2_file, "wb") as f:
            f.write(b"0" * (1024 * 1024 * 2))

        # Episode 1 is NOT on disk (was deleted by user)
        self.mock_config["download_dir"] = dl_dir

        ep1 = MagicMock(id="EP-1", episode_number=1, season_number=1, title="DOG & CHAINSAW", season_title="Chainsaw Man")
        ep2 = MagicMock(id="EP-2", episode_number=2, season_number=1, title="ARRIVAL IN TOKYO", season_title="Chainsaw Man")
        mock_get_series.return_value = {"episodes": [ep1, ep2]}

        # Seed series in store with both episodes marked downloaded previously
        data = self.store.load()
        data["series"]["SERIES-DISK"] = {
            "id": "SERIES-DISK",
            "title": "Chainsaw Man",
            "mode": "all_missing",
            "known_episodes": ["EP-1", "EP-2"],
            "downloaded_episodes": ["EP-1", "EP-2"],
            "status": "active",
        }
        self.store.save(data)

        # Run check
        res = self.watcher.check_series("SERIES-DISK")
        self.assertTrue(res["success"])

        # Should detect that EP-1 is missing from disk and enqueue it, while skipping EP-2
        self.mock_queue.enqueue_batch.assert_called_once()
        args, _ = self.mock_queue.enqueue_batch.call_args
        enqueued_items = args[0]
        self.assertEqual(len(enqueued_items), 1)
        self.assertEqual(enqueued_items[0]["id"], "EP-1")
        self.assertEqual(enqueued_items[0]["title"], "DOG & CHAINSAW")


if __name__ == "__main__":
    unittest.main()


class TestWatcherAudioReadiness(unittest.TestCase):
    """Issue #24: with audio fallback off, episodes not yet dubbed in the
    requested language must stay pending instead of being skipped forever."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store_file = os.path.join(self.temp_dir, "test_monitored.json")
        self.store = MonitoredStore(self.store_file)

        self.mock_queue = MagicMock()
        self.mock_queue.enqueue_batch.return_value = ["job-1"]
        self.mock_client = MagicMock()
        self.mock_config = {
            "audio_lang": "fr-FR",
            "subs_lang": "en-US",
            "video_quality": "1080p",
            "audio_quality": "192k",
            "download_dir": os.path.join(self.temp_dir, "no-such-dir"),
            "workers": 16,
            "audio_fallback": False,
        }
        self.watcher = SeriesWatcher(
            queue=self.mock_queue,
            client_factory=lambda: self.mock_client,
            config_provider=lambda: self.mock_config,
            store=self.store,
        )

    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    @staticmethod
    def _ep(ep_id, locales):
        from crunchyroll.types import DubVersion
        versions = [
            DubVersion(guid=f"g-{ep_id}-{loc}", media_guid="", season_guid="", audio_locale=loc, locale="")
            for loc in locales
        ]
        return MagicMock(id=ep_id, episode_number=1, season_number=1,
                         title=f"Ep {ep_id}", season_title="S1",
                         audio_locale=locales[0] if locales else "",
                         versions=versions)

    @patch("crunchyroll.api.get_series")
    def test_add_series_leaves_undubbed_episodes_pending(self, mock_get_series):
        ep_ja = self._ep("EP-1", ["ja-JP"])
        ep_fr = self._ep("EP-2", ["ja-JP", "fr-FR"])
        mock_get_series.return_value = {"episodes": [ep_ja, ep_fr], "title": "Show", "poster": ""}

        rec = self.watcher.add_series("SERIES-DUB", "Show", mode="latest_only")
        self.assertEqual(rec["known_episodes"], ["EP-2"])

    @patch("crunchyroll.api.get_series")
    def test_undubbed_episode_is_retried_until_dub_arrives(self, mock_get_series):
        ep_ja = self._ep("EP-1", ["ja-JP"])
        mock_get_series.return_value = {"episodes": [ep_ja], "title": "Show", "poster": ""}

        self.watcher.add_series("SERIES-DUB", "Show", mode="latest_only")
        res = self.watcher.check_series("SERIES-DUB")
        self.assertEqual(res["new_episodes"], 0)
        self.mock_queue.enqueue_batch.assert_not_called()

        # The episode must NOT have been swallowed into known_episodes
        data = self.store.load()
        self.assertNotIn("EP-1", data["series"]["SERIES-DUB"]["known_episodes"])

        # Dub drops: the same episode is now queued
        ep_dubbed = self._ep("EP-1", ["ja-JP", "fr-FR"])
        mock_get_series.return_value = {"episodes": [ep_dubbed], "title": "Show", "poster": ""}
        res = self.watcher.check_series("SERIES-DUB")
        self.assertEqual(res["new_episodes"], 1)
        self.mock_queue.enqueue_batch.assert_called_once()
        data = self.store.load()
        self.assertIn("EP-1", data["series"]["SERIES-DUB"]["known_episodes"])

    @patch("crunchyroll.api.get_series")
    def test_fallback_on_keeps_current_behavior(self, mock_get_series):
        self.mock_config["audio_fallback"] = True
        ep_ja = self._ep("EP-1", ["ja-JP"])
        mock_get_series.return_value = {"episodes": [ep_ja], "title": "Show", "poster": ""}

        rec = self.watcher.add_series("SERIES-FB", "Show", mode="latest_only")
        self.assertEqual(rec["known_episodes"], ["EP-1"])

    @patch("crunchyroll.api.get_series")
    def test_all_missing_does_not_requeue_undubbed(self, mock_get_series):
        ep_ja = self._ep("EP-1", ["ja-JP"])
        mock_get_series.return_value = {"episodes": [ep_ja], "title": "Show", "poster": ""}

        self.watcher.add_series("SERIES-AM", "Show", mode="all_missing")
        res = self.watcher.check_series("SERIES-AM")
        self.assertEqual(res["new_episodes"], 0)
        self.mock_queue.enqueue_batch.assert_not_called()

        # Once dubbed, all_missing queues it
        ep_dubbed = self._ep("EP-1", ["ja-JP", "fr-FR"])
        mock_get_series.return_value = {"episodes": [ep_dubbed], "title": "Show", "poster": ""}
        res = self.watcher.check_series("SERIES-AM")
        self.assertEqual(res["new_episodes"], 1)


class TestWatcherAudioReadinessEdgeCases(unittest.TestCase):
    """PR #25 review follow-ups: empty versions must trigger the detail
    lookup, and a failed lookup must leave the episode pending."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store_file = os.path.join(self.temp_dir, "test_monitored.json")
        self.store = MonitoredStore(self.store_file)

        self.mock_queue = MagicMock()
        self.mock_queue.enqueue_batch.return_value = ["job-1"]
        self.mock_client = MagicMock()
        self.mock_config = {
            "audio_lang": "fr-FR",
            "subs_lang": "en-US",
            "video_quality": "1080p",
            "audio_quality": "192k",
            "download_dir": os.path.join(self.temp_dir, "no-such-dir"),
            "workers": 16,
            "audio_fallback": False,
        }
        self.watcher = SeriesWatcher(
            queue=self.mock_queue,
            client_factory=lambda: self.mock_client,
            config_provider=lambda: self.mock_config,
            store=self.store,
        )

    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    @staticmethod
    def _detail_info(locales):
        from crunchyroll.types import DubVersion, EpisodeInfo, EpisodeMetadata
        versions = [
            DubVersion(guid=f"g-{loc}", media_guid="", season_guid="", audio_locale=loc, locale="")
            for loc in locales
        ]
        meta = EpisodeMetadata(
            audio_locale=locales[0] if locales else "",
            episode_number=5, season_number=1, series_title="Show",
            availability_starts="", versions=versions, season_title="S1",
        )
        return EpisodeInfo(episode_metadata=meta, title="Ep 5", subtitles={})

    @patch("crunchyroll.api.get_episode_info")
    @patch("crunchyroll.api.get_series")
    def test_empty_versions_in_listing_trigger_detail_lookup(self, mock_get_series, mock_info):
        # Listing carries a base audio_locale but NO versions array; the
        # detailed endpoint knows the French dub is actually available.
        ep = MagicMock(id="EP-9", episode_number=9, season_number=1, title="Ep 9",
                       season_title="S1", audio_locale="ja-JP", versions=[])
        mock_get_series.return_value = {"episodes": [ep], "title": "Show", "poster": ""}
        mock_info.return_value = self._detail_info(["ja-JP"])

        rec = self.watcher.add_series("SERIES-DETAIL", "Show", mode="latest_only")
        mock_info.assert_called()
        self.assertEqual(rec["known_episodes"], [])

        # The dub drops: the detail endpoint now lists fr-FR, and the same
        # listing (still without versions) must be re-checked in depth.
        mock_info.return_value = self._detail_info(["ja-JP", "fr-FR"])
        res = self.watcher.check_series("SERIES-DETAIL")
        self.assertEqual(res["new_episodes"], 1)
        self.mock_queue.enqueue_batch.assert_called_once()

    @patch("crunchyroll.api.get_episode_info")
    @patch("crunchyroll.api.get_series")
    def test_failed_detail_lookup_keeps_episode_pending(self, mock_get_series, mock_info):
        # No versions anywhere in the listing; the detail lookup times out.
        # The episode must stay pending and be retried, not marked known.
        ep = MagicMock(id="EP-7", episode_number=7, season_number=1, title="Ep 7",
                       season_title="S1", audio_locale="", versions=[])
        mock_get_series.return_value = {"episodes": [ep], "title": "Show", "poster": ""}
        mock_info.side_effect = RuntimeError("timeout")

        rec = self.watcher.add_series("SERIES-FLAKY", "Show", mode="latest_only")
        self.assertEqual(rec["known_episodes"], [])

        res = self.watcher.check_series("SERIES-FLAKY")
        self.assertEqual(res["new_episodes"], 0)
        self.mock_queue.enqueue_batch.assert_not_called()
        data = self.store.load()
        self.assertNotIn("EP-7", data["series"]["SERIES-FLAKY"]["known_episodes"])

        # The API recovers on a later pass: the dub is found and queued.
        mock_info.side_effect = None
        mock_info.return_value = self._detail_info(["ja-JP", "fr-FR"])
        res = self.watcher.check_series("SERIES-FLAKY")
        self.assertEqual(res["new_episodes"], 1)
        self.mock_queue.enqueue_batch.assert_called_once()
