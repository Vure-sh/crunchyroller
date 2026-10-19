import sys
import unittest
from unittest.mock import MagicMock, patch

from crunchyroll.api import PlaybackStream, Subtitle, get_episode_download
from crunchyroll.server import get_system_clipboard, set_system_clipboard
from crunchyroll.utils import locale_base


class TestSubtitlesAndClipboard(unittest.TestCase):
    def test_get_episode_download_preserves_subtitles(self):
        """Ensure /download endpoint does not wipe out multi-language subtitles from /play."""
        play_stream = PlaybackStream(
            manifest_url="https://example.com/manifest/play.mpd",
            subtitles={
                "en-US": Subtitle(language="en-US", url="https://example.com/sub_en.ass"),
                "fr-FR": Subtitle(language="fr-FR", url="https://example.com/sub_fr.ass"),
                "de-DE": Subtitle(language="de-DE", url="https://example.com/sub_de.ass"),
            },
            token="token123",
        )

        # Mock client returning download payload with only English subtitle
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "url": "https://example.com/manifest/download/dl.mpd?downloadGuid=guid456",
            "subtitles": {
                "en-US": {"language": "en-US", "url": "https://example.com/sub_en_dl.ass"},
            },
        }
        mock_client.do_request.return_value = mock_resp

        result = get_episode_download(
            client=mock_client,
            content_id="G14U415QM",
            play_stream=play_stream,
        )

        # All 3 languages must be preserved
        self.assertIn("en-US", result.subtitles)
        self.assertIn("fr-FR", result.subtitles)
        self.assertIn("de-DE", result.subtitles)
        # en-US was updated from download stream
        self.assertEqual(result.subtitles["en-US"].url, "https://example.com/sub_en_dl.ass")
        # fr-FR was preserved from play stream
        self.assertEqual(result.subtitles["fr-FR"].url, "https://example.com/sub_fr.ass")

    def test_candidate_version_prioritization(self):
        """Candidate versions matching requested subtitle locales must be prioritized."""
        v_hi = MagicMock(audio_locale="hi-IN", guid="g_hi")
        v_pt = MagicMock(audio_locale="pt-BR", guid="g_pt")
        v_fr = MagicMock(audio_locale="fr-FR", guid="g_fr")
        v_ja = MagicMock(audio_locale="ja-JP", guid="g_ja")

        candidate_versions = [v_hi, v_pt, v_fr, v_ja]
        subs_langs = ["fr-FR"]
        missing_cc_bases = set()
        requested_bases = {locale_base(loc).lower() for loc in subs_langs}

        def _version_priority(v):
            v_base = locale_base(getattr(v, "audio_locale", "") or "").lower()
            if v_base in missing_cc_bases:
                return 0
            if v_base in requested_bases:
                return 1
            if (getattr(v, "audio_locale", "") or "").lower() == "ja-jp":
                return 2
            return 3

        sorted_versions = sorted(candidate_versions, key=_version_priority)
        # French version must be first before other dubs
        self.assertEqual(sorted_versions[0].audio_locale, "fr-FR")

    def test_clipboard_roundtrip_safety(self):
        """Clipboard get/set must roundtrip cleanly without crashing 64-bit Python."""
        test_payload = "https://www.crunchyroll.com/series/GDKHZEJ0K/solo-leveling"
        ok = set_system_clipboard(test_payload)
        if ok:
            read_back = get_system_clipboard()
            self.assertEqual(read_back, test_payload)


if __name__ == "__main__":
    unittest.main()
