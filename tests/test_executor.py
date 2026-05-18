"""Tests for the executor service — rename logic and dry-run behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from duplicate_evaluator.models.file_entry import ActionType, FileAction
from duplicate_evaluator.services.executor import _compute_rename, execute_actions


class TestComputeRename:
    """Unit tests for the rename logic."""

    def test_underscore_to_space(self, tmp_path: Path):
        f = tmp_path / "my_song_name.mp4"
        result = _compute_rename(f)
        assert result.stem == "my song name"

    def test_camelcase_split(self, tmp_path: Path):
        f = tmp_path / "MySongName.mp4"
        result = _compute_rename(f)
        assert result.stem == "My Song Name"

    def test_mixed_underscore_and_camel(self, tmp_path: Path):
        f = tmp_path / "mySong_Name_HD.mp4"
        result = _compute_rename(f)
        # Underscores → spaces, camelCase split, then spaces collapsed:
        # "mySong_Name_HD" → "mySong Name HD" → "my Song Name HD"
        assert result.stem == "my Song Name HD"
        assert "  " not in result.stem  # no double spaces after collapse

    def test_collapse_spaces(self, tmp_path: Path):
        f = tmp_path / "song__double.mp4"
        result = _compute_rename(f)
        assert "  " not in result.stem

    def test_extension_preserved(self, tmp_path: Path):
        f = tmp_path / "my_song.mp4"
        result = _compute_rename(f)
        assert result.suffix == ".mp4"

    def test_clean_name_unchanged(self, tmp_path: Path):
        f = tmp_path / "Clean Song Name.mp4"
        result = _compute_rename(f)
        assert result.stem == "Clean Song Name"


class TestExecuteActions:
    def test_dry_run_delete_does_not_delete(self, tmp_path: Path):
        f = tmp_path / "test.mp4"
        f.write_bytes(b"data")
        action = FileAction(filename="test.mp4", path=str(f), action=ActionType.DELETE)
        lines = execute_actions([action], dry_run=True)
        assert f.exists(), "File should still exist after dry run"
        assert any("DRY RUN" in l or "DELETE" in l for l in lines)

    def test_real_delete(self, tmp_path: Path):
        f = tmp_path / "deleteme.mp4"
        f.write_bytes(b"data")
        action = FileAction(filename="deleteme.mp4", path=str(f), action=ActionType.DELETE)
        lines = execute_actions([action], dry_run=False)
        assert not f.exists(), "File should be deleted"
        assert any("Deleted" in l or "DELETE" in l for l in lines)

    def test_dry_run_rename_does_not_rename(self, tmp_path: Path):
        f = tmp_path / "my_song.mp4"
        f.write_bytes(b"data")
        action = FileAction(filename="my_song.mp4", path=str(f), action=ActionType.RENAME)
        lines = execute_actions([action], dry_run=True)
        assert f.exists(), "Original file should still exist after dry run"

    def test_real_rename(self, tmp_path: Path):
        f = tmp_path / "my_song.mp4"
        f.write_bytes(b"data")
        action = FileAction(filename="my_song.mp4", path=str(f), action=ActionType.RENAME)
        lines = execute_actions([action], dry_run=False)
        assert not f.exists(), "Original file should be gone"
        renamed = tmp_path / "my song.mp4"
        assert renamed.exists(), "Renamed file should exist"

    def test_keep_action_is_noop(self, tmp_path: Path):
        f = tmp_path / "keep_me.mp4"
        f.write_bytes(b"data")
        action = FileAction(filename="keep_me.mp4", path=str(f), action=ActionType.KEEP)
        lines = execute_actions([action], dry_run=False)
        assert f.exists()
        # KEEP actions should not appear in log lines (only summary)
        assert not any("keep_me" in l for l in lines)

    def test_missing_file(self, tmp_path: Path):
        action = FileAction(filename="ghost.mp4", path=str(tmp_path / "ghost.mp4"), action=ActionType.DELETE)
        lines = execute_actions([action], dry_run=False)
        assert any("not found" in l or "SKIP" in l for l in lines)

    def test_summary_line_always_present(self, tmp_path: Path):
        lines = execute_actions([], dry_run=True)
        assert any("COMPLETE" in l for l in lines)
