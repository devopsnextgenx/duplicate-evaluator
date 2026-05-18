"""Tests for the reporter service — JSON save/load round-trip."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from duplicate_evaluator.models.file_entry import (
    ActionType,
    AnalysisMode,
    FileEntry,
    FolderReport,
    QualityTier,
    ReportEntry,
)
from duplicate_evaluator.services.reporter import load_report, report_path, save_report


@pytest.fixture
def sample_report(tmp_path: Path) -> FolderReport:
    entry = ReportEntry(
        file=FileEntry(
            filename="SongOne.mp4",
            path=str(tmp_path / "SongOne.mp4"),
            size_bytes=1024000,
            language="Hindi",
            quality=QualityTier.HD,
            actress="Actress1",
        ),
        is_duplicate=True,
        needs_rename=False,
        confidence=0.92,
        reason="Duplicate of SongOneHD.mp4",
        suggested_action=ActionType.DELETE,
    )
    return FolderReport(
        folder_path=str(tmp_path),
        language="Hindi",
        quality=QualityTier.HD,
        actress="Actress1",
        mode=AnalysisMode.WITHIN_FOLDER,
        entries=[entry],
        llm_model="llama3.2",
        total_files_scanned=3,
    )


class TestReporter:
    def test_save_creates_file(self, tmp_path: Path, sample_report: FolderReport):
        saved = save_report(sample_report)
        assert saved.exists()
        assert saved.name == "_report.json"

    def test_load_returns_report(self, tmp_path: Path, sample_report: FolderReport):
        save_report(sample_report)
        loaded = load_report(str(tmp_path))
        assert loaded is not None
        assert loaded.actress == "Actress1"
        assert loaded.language == "Hindi"

    def test_round_trip_entries(self, tmp_path: Path, sample_report: FolderReport):
        save_report(sample_report)
        loaded = load_report(str(tmp_path))
        assert len(loaded.entries) == 1
        assert loaded.entries[0].is_duplicate is True
        assert abs(loaded.entries[0].confidence - 0.92) < 1e-6

    def test_load_missing_returns_none(self, tmp_path: Path):
        result = load_report(str(tmp_path / "nonexistent"))
        assert result is None

    def test_computed_counts(self, tmp_path: Path, sample_report: FolderReport):
        save_report(sample_report)
        loaded = load_report(str(tmp_path))
        assert loaded.duplicate_count == 1
        assert loaded.rename_count == 0

    def test_report_path_helper(self, tmp_path: Path):
        p = report_path(str(tmp_path))
        assert p.name == "_report.json"
        assert p.parent == tmp_path
