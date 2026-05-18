"""Tests for the folder scanner service."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from duplicate_evaluator.services.scanner import (
    build_folder_tree,
    scan_actress_folder,
    scan_cross_quality,
)


@pytest.fixture
def sample_media_root(tmp_path: Path) -> Path:
    """Create a minimal media folder hierarchy for testing."""
    for lang in ("Hindi", "English"):
        for quality in ("xhd", "hd", "sd"):
            actress_dir = tmp_path / lang / quality / "Actress1"
            actress_dir.mkdir(parents=True)
            # Create some MP4 files
            (actress_dir / "SongOne.mp4").write_bytes(b"\x00" * 1024)
            (actress_dir / "song_two.mp4").write_bytes(b"\x00" * 2048)
            (actress_dir / "SongOneHD.mp4").write_bytes(b"\x00" * 512)  # likely duplicate

    return tmp_path


class TestScanActressFolder:
    def test_scans_mp4_files(self, sample_media_root: Path):
        folder = sample_media_root / "Hindi" / "hd" / "Actress1"
        entries = scan_actress_folder(str(folder))
        assert len(entries) == 3
        filenames = [e.filename for e in entries]
        assert "SongOne.mp4" in filenames
        assert "song_two.mp4" in filenames

    def test_detects_quality(self, sample_media_root: Path):
        folder = sample_media_root / "Hindi" / "hd" / "Actress1"
        entries = scan_actress_folder(str(folder))
        assert all(e.quality.value == "hd" for e in entries)

    def test_detects_language(self, sample_media_root: Path):
        folder = sample_media_root / "Hindi" / "xhd" / "Actress1"
        entries = scan_actress_folder(str(folder))
        assert all(e.language == "Hindi" for e in entries)

    def test_empty_folder(self, tmp_path: Path):
        (tmp_path / "empty").mkdir()
        entries = scan_actress_folder(str(tmp_path / "empty"))
        assert entries == []

    def test_nonexistent_path(self):
        entries = scan_actress_folder("/nonexistent/path/xyz")
        assert entries == []

    def test_file_sizes(self, sample_media_root: Path):
        folder = sample_media_root / "Hindi" / "hd" / "Actress1"
        entries = scan_actress_folder(str(folder))
        size_map = {e.filename: e.size_bytes for e in entries}
        assert size_map["SongOne.mp4"] == 1024
        assert size_map["song_two.mp4"] == 2048


class TestScanCrossQuality:
    def test_returns_all_tiers(self, sample_media_root: Path):
        result = scan_cross_quality("Hindi", "Actress1", str(sample_media_root))
        assert "xhd" in result
        assert "hd" in result
        assert "sd" in result

    def test_each_tier_has_files(self, sample_media_root: Path):
        result = scan_cross_quality("Hindi", "Actress1", str(sample_media_root))
        assert len(result["xhd"]) == 3
        assert len(result["hd"])  == 3
        assert len(result["sd"])  == 3

    def test_missing_actress_returns_empty(self, sample_media_root: Path):
        result = scan_cross_quality("Hindi", "NoSuchActress", str(sample_media_root))
        assert result["xhd"] == []
        assert result["hd"]  == []
        assert result["sd"]  == []


class TestBuildFolderTree:
    def test_tree_structure(self, sample_media_root: Path):
        tree = build_folder_tree(str(sample_media_root))
        assert tree["type"] == "root"
        lang_names = [c["name"] for c in tree["children"]]
        assert "Hindi" in lang_names
        assert "English" in lang_names

    def test_quality_nodes(self, sample_media_root: Path):
        tree = build_folder_tree(str(sample_media_root))
        hindi = next(c for c in tree["children"] if c["name"] == "Hindi")
        quality_names = [c["name"] for c in hindi["children"]]
        assert "hd" in quality_names
        assert "xhd" in quality_names
        assert "sd" in quality_names

    def test_actress_nodes(self, sample_media_root: Path):
        tree = build_folder_tree(str(sample_media_root))
        hindi = next(c for c in tree["children"] if c["name"] == "Hindi")
        hd    = next(c for c in hindi["children"] if c["name"] == "hd")
        actress = hd["children"][0]
        assert actress["name"] == "Actress1"
        assert actress["type"] == "actress"
        assert actress["mp4_count"] == 3

    def test_nonexistent_root(self, tmp_path: Path):
        tree = build_folder_tree(str(tmp_path / "doesnotexist"))
        assert "error" in tree
