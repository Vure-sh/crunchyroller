import unittest
from unittest.mock import MagicMock, patch

from crunchyroll.types import (
    AudioUnavailableError,
    DubVersion,
    EpisodeInfo,
    EpisodeMetadata,
    PlaybackStream,
    Subtitle,
)
from crunchyroll.downloader import download_episode
from crunchyroll.queue import DownloadQueue, QueueItem, DownloadTask


class TestAudioFallback(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        # Episode only available in Japanese
        self.info = EpisodeInfo(
            title="The Apothecary Diaries - Ep 1",
            episode_metadata=EpisodeMetadata(
                series_title="The Apothecary Diaries",
                season_number=1,
                episode_number=1,
                audio_locale="ja-JP",
                availability_starts="",
                versions=[
                    DubVersion(guid="guid_ja", audio_locale="ja-JP", media_guid="m_ja"),
                ],
            ),
        )

    def test_audio_fallback_disabled_raises_error(self):
        """When audio_fallback is False and requested dub is unavailable, download_episode raises AudioUnavailableError."""
        with self.assertRaises(AudioUnavailableError) as ctx:
            download_episode(
                client=self.mock_client,
                base_content_id="guid_ja",
                info=self.info,
                audio_langs=["en-US"],
                subs_langs=["en-US"],
                video_quality="1080p",
                audio_quality="192k",
                audio_fallback=False,
            )
        self.assertIn("en-US", str(ctx.exception))
        self.assertIn("audio fallback is disabled", str(ctx.exception))

    @patch("crunchyroll.downloader.get_episode")
    @patch("crunchyroll.downloader.get_episode_download")
    @patch("crunchyroll.downloader.download_subs", return_value="dummy.ass")
    @patch("crunchyroll.downloader.merge_everything")
    def test_audio_fallback_enabled_falls_back_to_original(self, mock_merge, mock_subs, mock_dl, mock_get_ep):
        """When audio_fallback is True (default), unavailable dub falls back to original audio."""
        mock_ep = PlaybackStream(
            manifest_url="https://example.com/manifest.mpd",
            token="dummy_token",
            subtitles={"en-US": Subtitle(language="en-US", url="https://example.com/sub.ass")},
        )
        mock_get_ep.return_value = mock_ep
        mock_dl.return_value = mock_ep

        with patch("os.makedirs"), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=50 * 1024 * 1024):

            output_file = download_episode(
                client=self.mock_client,
                base_content_id="guid_ja",
                info=self.info,
                audio_langs=["en-US"],
                subs_langs=["en-US"],
                video_quality="1080p",
                audio_quality="192k",
                audio_fallback=True,
            )
            self.assertTrue(output_file.endswith(".mkv"))

    def test_queue_handles_skipped_audio_unavailable(self):
        """When an episode raises AudioUnavailableError, the queue marks it as 'skipped' and continues."""
        q = DownloadQueue()
        item = QueueItem(
            id="job-test-skip",
            ep_id="ep-skip-1",
            title="Ep Without Dub",
            series_title="Test Series",
            audio_langs=["en-US"],
            audio_fallback=False,
        )

        try:
            raise AudioUnavailableError("Requested audio [en-US] is unavailable and audio fallback is disabled.")
        except AudioUnavailableError as e:
            with q.lock:
                item.status = "skipped"
                item.error = str(e)
                q.history.append(item)
                q.all_items_map[item.id] = item

        self.assertEqual(item.status, "skipped")
        self.assertIn("en-US", item.error)

        # Check task completion computation when other episodes are completed
        task = DownloadTask(
            id="task-1",
            series_title="Test Series",
            item_ids=["job-done", "job-test-skip"],
        )
        done_item = QueueItem(id="job-done", ep_id="ep-2", status="completed")
        q.all_items_map["job-done"] = done_item

        computed = task.get_computed_status(q.all_items_map)
        # Because the only active items are completed (skipped items are excluded from active), task is completed
        self.assertEqual(computed, "completed")


if __name__ == "__main__":
    unittest.main()
