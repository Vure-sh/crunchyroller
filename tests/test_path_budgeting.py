import os
import unittest
from unittest.mock import MagicMock, patch

from crunchyroll.utils import (
    OutputPathInfo,
    build_output_path,
    resolve_season_folder,
    sanitize_filename,
)
from crunchyroll.merger import generate_ffmetadata


class TestPathBudgeting(unittest.TestCase):
    def test_short_path_unchanged(self):
        """Short paths must remain 100% intact for backward compatibility."""
        base_dir = r"F:\Ani-Download"
        series_title = "Frieren: Beyond Journey's End"
        season_folder = "Season 01"
        season_num = 1
        ep_num = 1
        ep_title = "The Journey's End"
        quality_tag = " [1080p]"
        ext = ".mkv"

        res = build_output_path(
            base_dir=base_dir,
            series_title=series_title,
            season_folder=season_folder,
            season_num=season_num,
            ep_num=ep_num,
            ep_title=ep_title,
            quality_tag=quality_tag,
            ext=ext,
            max_path_length=259,
        )

        expected_filename = "Frieren - Beyond Journey_s End - S01E01 - The Journey_s End [1080p].mkv"
        self.assertEqual(res.filename, expected_filename)
        self.assertEqual(res.filename, res.original_filename)
        self.assertEqual(res.stem, res.original_stem)
        self.assertTrue(len(res.output_filename) + 21 <= 259)

    def test_issue_17_long_path_budgeting(self):
        """
        Issue #17 repro:
        Series: 'A Livid Lady's Guide to Getting Even: How I Crushed My Homeland with My Mighty Grimoires'
        Episode: 'The Tragedy of the House of Count Arty' (S01E08)
        Without budgeting, output_filename + .tmp.mkv.chapters.txt exceeds 280+ chars.
        With budgeting, the longest temporary derived path stays safely <= 259 chars.
        """
        base_dir = r"F:\Ani-Download"
        series_title = "A Livid Lady's Guide to Getting Even: How I Crushed My Homeland with My Mighty Grimoires"
        season_folder = "Season 01"
        season_num = 1
        ep_num = 8
        ep_title = "The Tragedy of the House of Count Arty"
        quality_tag = " [1080p]"
        ext = ".mkv"

        res = build_output_path(
            base_dir=base_dir,
            series_title=series_title,
            season_folder=season_folder,
            season_num=season_num,
            ep_num=ep_num,
            ep_title=ep_title,
            quality_tag=quality_tag,
            ext=ext,
            max_path_length=259,
            temp_suffix_buffer=21,
        )

        # Longest derived temporary file during muxing
        longest_derived_path = res.output_filename + ".tmp.mkv.chapters.txt"
        temp_mux_target = res.output_filename + ".tmp.mkv"

        self.assertLessEqual(len(longest_derived_path), 259)
        self.assertLessEqual(len(temp_mux_target), 259)
        self.assertLessEqual(len(res.output_filename), 259)

        # Critical elements MUST be preserved
        self.assertIn("S01E08", res.filename)
        self.assertIn("[1080p].mkv", res.filename)
        self.assertTrue(res.filename.startswith("A Livid Lady_s Guide to Getting Even"))
        self.assertNotEqual(res.filename, res.original_filename)

    def test_deep_directory_series_truncation(self):
        """When base directory is deep, series title in filename is also safely budgeted."""
        base_dir = r"F:\Very\Deep\Anime\Library\Directory\That\Consumes\A\Lot\Of\Characters\On\Disk"
        series_title = "A Livid Lady's Guide to Getting Even: How I Crushed My Homeland with My Mighty Grimoires"
        season_folder = "Season 01"
        season_num = 1
        ep_num = 8
        ep_title = "The Tragedy of the House of Count Arty"
        quality_tag = " [1080p]"
        ext = ".mkv"

        res = build_output_path(
            base_dir=base_dir,
            series_title=series_title,
            season_folder=season_folder,
            season_num=season_num,
            ep_num=ep_num,
            ep_title=ep_title,
            quality_tag=quality_tag,
            ext=ext,
            max_path_length=259,
            temp_suffix_buffer=21,
        )

        longest_derived = res.output_filename + ".tmp.mkv.chapters.txt"
        self.assertLessEqual(len(longest_derived), 259)
        self.assertIn("S01E08", res.filename)
        self.assertIn("[1080p].mkv", res.filename)

    def test_standalone_audio_mode_budgeting(self):
        """Standalone audio mode creates an episode subfolder; both folder and file must fit."""
        base_dir = r"F:\Ani-Download"
        series_title = "A Livid Lady's Guide to Getting Even: How I Crushed My Homeland with My Mighty Grimoires"
        season_folder = "Season 01"
        season_num = 1
        ep_num = 8
        ep_title = "The Tragedy of the House of Count Arty"
        quality_tag = " [audio]"
        ext = ".m4a"

        res = build_output_path(
            base_dir=base_dir,
            series_title=series_title,
            season_folder=season_folder,
            season_num=season_num,
            ep_num=ep_num,
            ep_title=ep_title,
            quality_tag=quality_tag,
            ext=ext,
            ep_subfolder=True,
            max_path_length=259,
            temp_suffix_buffer=21,
        )

        longest_derived = res.output_filename + ".tmp.m4a.chapters.txt"
        self.assertLessEqual(len(longest_derived), 259)
        self.assertIn("S01E08", res.filename)
        self.assertIn("[audio].m4a", res.filename)

        # Companion subtitle path check
        sub_dest = os.path.join(res.output_dir, f"{res.stem}.en-US-cc.ass")
        self.assertLessEqual(len(sub_dest), 259)

    def test_clean_punctuation_trimming(self):
        """Trimmed titles must not leave dangling dots, hyphens, or spaces for Windows."""
        res = build_output_path(
            base_dir=r"F:\Ani-Download",
            series_title="A Livid Lady's Guide to Getting Even: How I Crushed My Homeland with My Mighty Grimoires",
            season_folder="Season 01",
            season_num=1,
            ep_num=8,
            ep_title="The Tragedy of the House of Count Arty",
            quality_tag=" [1080p]",
            ext=".mkv",
            max_path_length=259,
        )
        stem_without_tag = res.stem
        self.assertFalse(stem_without_tag.endswith("."))
        self.assertFalse(stem_without_tag.endswith("-"))
        self.assertFalse(stem_without_tag.endswith(" "))
        self.assertFalse(stem_without_tag.endswith("_"))

    def test_ffmetadata_generation(self):
        """Chapters ffmetadata generates cleanly without syntax errors."""
        chapters = [
            {"start": 0.0, "end": 90.0, "name": "Intro"},
            {"start": 90.0, "end": 1350.0, "name": "Episode"},
            {"start": 1350.0, "end": 1440.0, "name": "Credits"},
        ]
        meta = generate_ffmetadata(chapters)
        self.assertIn(";FFMETADATA1", meta)
        self.assertIn("[CHAPTER]", meta)
        self.assertIn("START=0", meta)
        self.assertIn("title=Intro", meta)
        self.assertIn("title=Episode", meta)
        self.assertIn("title=Credits", meta)


if __name__ == "__main__":
    unittest.main()
