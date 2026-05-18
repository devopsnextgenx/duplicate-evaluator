"""Tests for the API action persistence and manual execution markers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duplicate_evaluator.models.file_entry import (
    ActionType,
    AnalysisMode,
    FileEntry,
    FolderReport,
    QualityTier,
    ReportEntry,
)
from duplicate_evaluator.services.reporter import load_report, save_report
from duplicate_evaluator.main import app

client = TestClient(app)


@pytest.fixture
def sample_report_data(tmp_path: Path) -> FolderReport:
    entry1 = ReportEntry(
        file=FileEntry(
            filename="VideoA.mp4",
            path=str(tmp_path / "VideoA.mp4"),
            size_bytes=1048576,
            language="English",
            quality=QualityTier.HD,
            actress="TestActress",
        ),
        is_duplicate=True,
        needs_rename=False,
        confidence=0.95,
        reason="Duplicate of VideoB.mp4",
        suggested_action=ActionType.KEEP,
    )
    entry2 = ReportEntry(
        file=FileEntry(
            filename="VideoB.mp4",
            path=str(tmp_path / "VideoB.mp4"),
            size_bytes=1048576,
            language="English",
            quality=QualityTier.HD,
            actress="TestActress",
        ),
        is_duplicate=False,
        needs_rename=True,
        confidence=0.80,
        reason="Has underscores",
        suggested_action=ActionType.KEEP,
    )
    return FolderReport(
        folder_path=str(tmp_path),
        language="English",
        quality=QualityTier.HD,
        actress="TestActress",
        mode=AnalysisMode.WITHIN_FOLDER,
        entries=[entry1, entry2],
        llm_model="test-llm",
        total_files_scanned=2,
    )


def test_update_report_actions_api(tmp_path: Path, sample_report_data: FolderReport):
    # Save the initial report first
    save_report(sample_report_data)

    # Let's send a batch persistence request to update suggested actions
    payload = {
        "folder_path": str(tmp_path),
        "actions": [
            {"path": str(tmp_path / "VideoA.mp4"), "action": "delete"},
            {"path": str(tmp_path / "VideoB.mp4"), "action": "rename"}
        ]
    }

    response = client.post("/api/report/actions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["updated_count"] == 2

    # Load report from disk and verify it has persisted correctly
    loaded = load_report(str(tmp_path))
    assert loaded is not None
    assert loaded.entries[0].suggested_action == ActionType.DELETE
    assert loaded.entries[1].suggested_action == ActionType.RENAME


def test_update_report_actions_not_found():
    payload = {
        "folder_path": "/nonexistent/folder/path",
        "actions": []
    }
    response = client.post("/api/report/actions", json=payload)
    assert response.status_code == 404


def test_mark_executed_api(tmp_path: Path):
    # Make sure _executed.json does not exist
    executed_file = tmp_path / "_executed.json"
    assert not executed_file.exists()

    payload = {"folder_path": str(tmp_path)}
    response = client.post("/api/execute/mark-executed", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "marked as executed" in data["message"]

    # Verify file was written
    assert executed_file.exists()
    content = json.loads(executed_file.read_text(encoding="utf-8"))
    assert content["manual"] is True
    assert len(content["actions"]) == 0


def test_mark_executed_not_found():
    payload = {"folder_path": "/nonexistent/folder/path"}
    response = client.post("/api/execute/mark-executed", json=payload)
    assert response.status_code == 404
