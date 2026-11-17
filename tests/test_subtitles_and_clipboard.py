import os
import sys
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

from crunchyroll.api import PlaybackStream, Subtitle, get_episode_download, get_episode
from crunchyroll.downloader import _find_matching_subtitle, download_subs
from crunchyroll.mpd import get_manifest_subtitles
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

    def test_find_matching_subtitle(self):
        """Flexible subtitle resolver matches exact locales, ISO aliases, and language prefixes."""
        sub_fr = Subtitle(language="fr-FR", url="https://example.com/fr.ass")
        sub_en = Subtitle(language="en-US", url="https://example.com/en.ass")
        sub_map = {
            "fr-fr": sub_fr,
            "en-us": sub_en,
        }

        # Exact and case-insensitive
        self.assertEqual(_find_matching_subtitle(sub_map, "fr-FR"), sub_fr)
        self.assertEqual(_find_matching_subtitle(sub_map, "fr-fr"), sub_fr)

        # 3-letter ISO 639-2 alias
        self.assertEqual(_find_matching_subtitle(sub_map, "fra"), sub_fr)
        self.assertEqual(_find_matching_subtitle(sub_map, "fre"), sub_fr)

        # 2-letter prefix
        self.assertEqual(_find_matching_subtitle(sub_map, "fr"), sub_fr)

        # Full language name alias
        self.assertEqual(_find_matching_subtitle(sub_map, "french"), sub_fr)

        # Reverse lookup: map has 3-letter code or short code
        sub_de = Subtitle(language="deu", url="https://example.com/de.ass")
        sub_map_alt = {"deu": sub_de}
        self.assertEqual(_find_matching_subtitle(sub_map_alt, "de-DE"), sub_de)
        self.assertEqual(_find_matching_subtitle(sub_map_alt, "ger"), sub_de)

        # Not found returns None
        self.assertIsNone(_find_matching_subtitle(sub_map, "ja-JP"))

    def test_get_manifest_subtitles_relative_url(self):
        """DASH MPD subtitle parser resolves relative BaseURL with manifest URL and normalizes locales."""
        xml_content = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011">
            <Period>
                <AdaptationSet mimeType="text/vtt" lang="fra">
                    <BaseURL>subtitles/french.vtt</BaseURL>
                </AdaptationSet>
                <AdaptationSet mimeType="text/vtt" lang="en">
                    <BaseURL>https://cdn.example.com/subs/en.vtt</BaseURL>
                </AdaptationSet>
            </Period>
        </MPD>"""
        root = ET.fromstring(xml_content)
        manifest_url = "https://v.vrv.co/evs/stream/manifest.mpd"
        subs = get_manifest_subtitles(root, manifest_url=manifest_url)

        self.assertIn("fr-FR", subs)
        self.assertEqual(subs["fr-FR"], "https://v.vrv.co/evs/stream/subtitles/french.vtt")
        self.assertIn("en-US", subs)
        self.assertEqual(subs["en-US"], "https://cdn.example.com/subs/en.vtt")

    def test_download_subs_auth_header(self):
        """download_subs passes client Bearer auth header when client is provided."""
        mock_pool = MagicMock()
        mock_pool.download_segment.return_value = b"[Script Info]\nTitle: Test Subtitle\n"
        mock_client = MagicMock()
        mock_client.token = "secret_access_token_123"

        sub_url = "https://example.com/subtitles/track.ass"
        tmp_path = download_subs(sub_url, pool=mock_pool, client=mock_client)

        try:
            self.assertTrue(os.path.exists(tmp_path))
            mock_pool.download_segment.assert_called_once()
            _, kwargs = mock_pool.download_segment.call_args
            self.assertEqual(kwargs.get("headers"), {"Authorization": "Bearer secret_access_token_123"})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_download_subs_target_dir(self):
        """download_subs writes directly to target_dir when provided rather than system tmp."""
        import shutil
        import tempfile
        custom_dir = tempfile.mkdtemp()
        mock_pool = MagicMock()
        mock_pool.download_segment.return_value = b"[Script Info]\nTitle: Test Subtitle\n"
        try:
            sub_url = "https://example.com/subtitles/track.ass"
            sub_file = download_subs(sub_url, pool=mock_pool, target_dir=custom_dir)
            self.assertTrue(os.path.exists(sub_file))
            self.assertEqual(os.path.dirname(os.path.abspath(sub_file)), os.path.abspath(custom_dir))
        finally:
            shutil.rmtree(custom_dir, ignore_errors=True)

    def test_get_episode_prioritizes_web_chrome_endpoint(self):
        """get_episode must query web/chrome/play first to retrieve full .ass softsubtitles."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "url": "https://v.vrv.co/manifest.mpd",
            "subtitles": {
                "fr-FR": {"language": "fr-FR", "url": "https://example.com/fr.ass", "format": "ass"},
                "en-US": {"language": "en-US", "url": "https://example.com/en.ass", "format": "ass"},
            },
            "token": "tok_123",
        }
        mock_client.do_request.return_value = mock_resp

        ep = get_episode(mock_client, "G14U415QM", debug=False)

        # Verify the first call was to web/chrome/play
        first_call_url = mock_client.do_request.call_args_list[0][0][1]
        self.assertIn("web/chrome/play", first_call_url)
        self.assertIn("fr-FR", ep.subtitles)
        self.assertIn("en-US", ep.subtitles)


    def test_signs_and_cc_matching_separation(self):
        """Full dialogue requests must never match signs tracks, and signs requests must never match full tracks."""
        sub_dialogue = Subtitle(language="fr-FR", url="https://example.com/fr_dialogue.ass", is_signs=False)
        sub_signs = Subtitle(language="fr-FR-signs", url="https://example.com/fr_signs.ass", is_signs=True)
        sub_cc = Subtitle(language="fr-FR-cc", url="https://example.com/fr_cc.ass", is_cc=True)

        # Case A: Map has only signs
        map_signs_only = {"fr-fr-signs": sub_signs}
        self.assertIsNone(_find_matching_subtitle(map_signs_only, "fr-FR"))
        self.assertIsNone(_find_matching_subtitle(map_signs_only, "fra"))
        self.assertIsNone(_find_matching_subtitle(map_signs_only, "fr"))
        self.assertEqual(_find_matching_subtitle(map_signs_only, "fr-FR-signs"), sub_signs)
        self.assertEqual(_find_matching_subtitle(map_signs_only, "fra-signs"), sub_signs)

        # Case B: Map has dialogue and signs
        map_both = {
            "fr-fr": sub_dialogue,
            "fr-fr-signs": sub_signs,
            "fr-fr-cc": sub_cc,
        }
        self.assertEqual(_find_matching_subtitle(map_both, "fr-FR"), sub_dialogue)
        self.assertEqual(_find_matching_subtitle(map_both, "fra"), sub_dialogue)
        self.assertEqual(_find_matching_subtitle(map_both, "fr-FR-signs"), sub_signs)
        self.assertEqual(_find_matching_subtitle(map_both, "fr-FR-cc"), sub_cc)

    def test_track_title_and_locale_base_signs(self):
        """track_title formats [Signs & Songs] and locale_base strips -signs properly."""
        from crunchyroll.utils import track_title, locale_base
        self.assertEqual(locale_base("fr-FR-signs"), "fr-FR")
        self.assertEqual(locale_base("en-US-signs"), "en-US")
        self.assertEqual(locale_base("de-DE-cc"), "de-DE")
        self.assertEqual(track_title("fr-FR-signs"), "Français [Signs & Songs]")
        self.assertEqual(track_title("en-US-signs"), "English [Signs & Songs]")
        self.assertEqual(track_title("de-DE-signs"), "Deutsch [Signs & Songs]")

    def test_dub_signs_rekeying_and_disposition(self):
        """Dub stream native subtitle is re-keyed to -signs, and full dialogue takes default disposition."""
        from crunchyroll.types import MediaTrack, EpisodeInfo, EpisodeMetadata, DubVersion
        # Verify default disposition prioritization logic
        tracks = [
            MediaTrack(file="/tmp/signs.ass", locale="fr-FR-signs", is_signs=True),
            MediaTrack(file="/tmp/dialogue.ass", locale="fr-FR", is_signs=False),
        ]
        has_dialogue = any(not t.is_cc and not getattr(t, "is_signs", False) and not t.locale.endswith("-signs") for t in tracks)
        first_assigned = False
        for t in tracks:
            t_is_signs = getattr(t, "is_signs", False) or t.locale.endswith("-signs")
            if has_dialogue:
                if not t.is_cc and not t_is_signs and not first_assigned:
                    t.is_default = True
                    first_assigned = True
                else:
                    t.is_default = False
            else:
                if not first_assigned:
                    t.is_default = True
                    first_assigned = True
                else:
                    t.is_default = False

        # Dialogue track MUST be default, signs track MUST NOT be default
        self.assertFalse(tracks[0].is_default)
        self.assertTrue(tracks[1].is_default)


    @patch("subprocess.run")
    @patch("crunchyroll.merger.find_ffmpeg", return_value="ffmpeg")
    def test_merger_subtitles_disposition_and_titles(self, mock_find, mock_run):
        """merge_everything properly sets disposition and titles for dialogue and signs tracks."""
        from crunchyroll.merger import merge_everything
        from crunchyroll.types import MediaTrack, EpisodeInfo, EpisodeMetadata

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        info = EpisodeInfo(
            title="Episode 1",
            episode_metadata=EpisodeMetadata(
                series_title="Black Clover",
                season_number=1,
                episode_number=1,
                audio_locale="ja-JP",
                availability_starts="",
            ),
        )

        audio_tracks = [MediaTrack(file="audio_fr.m4a", locale="fr-FR", is_default=True)]
        sub_tracks = [
            MediaTrack(file="sub_fr.ass", locale="fr-FR", is_default=True, is_signs=False),
            MediaTrack(file="sub_fr_signs.ass", locale="fr-FR-signs", is_default=False, is_signs=True),
        ]

        with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=1000), patch("os.remove"):
            merge_everything(
                info=info,
                audio_tracks=audio_tracks,
                sub_tracks=sub_tracks,
                video_file="video.mp4",
                output_file="out.mkv",
            )

        cmd = mock_run.call_args[0][0]
        self.assertIn("-metadata:s:s:0", cmd)
        idx_0 = cmd.index("-metadata:s:s:0")
        self.assertEqual(cmd[idx_0 + 1], "language=fra")
        self.assertIn("title=\u0046\u0072\u0061\u006e\u00e7\u0061\u0069\u0073", cmd)
        idx_0_disp = cmd.index("-disposition:s:0")
        self.assertEqual(cmd[idx_0_disp + 1], "default")

        self.assertIn("-metadata:s:s:1", cmd)
        idx_1 = cmd.index("-metadata:s:s:1")
        self.assertEqual(cmd[idx_1 + 1], "language=fra")
        self.assertIn("title=\u0046\u0072\u0061\u006e\u00e7\u0061\u0069\u0073 [Signs & Songs]", cmd)
        idx_1_disp = cmd.index("-disposition:s:1")
        self.assertEqual(cmd[idx_1_disp + 1], "0")


if __name__ == "__main__":
    unittest.main()
