"""Report persistence — save and load FolderReport as JSON alongside the media files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from duplicate_evaluator.models.file_entry import FolderReport

logger = logging.getLogger(__name__)

REPORT_FILENAME = "_report.json"
EXECUTED_FILENAME = "_executed.json"


def save_report(report: FolderReport) -> Path:
    """Persist a FolderReport to <folder_path>/_report.json."""
    target = Path(report.folder_path) / REPORT_FILENAME
    try:
        target.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info("Report saved: %s", target)
    except OSError as exc:
        logger.error("Failed to save report to %s: %s", target, exc)
        raise
    return target


def load_report(folder_path: str) -> Optional[FolderReport]:
    """Load a FolderReport from <folder_path>/_report.json, or None if missing."""
    target = Path(folder_path) / REPORT_FILENAME
    if not target.exists():
        logger.debug("No report file at %s", target)
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        report = FolderReport.model_validate(data)
        
        # Dynamically check if files have been deleted
        for entry in report.entries:
            if not Path(entry.file.path).exists():
                entry.deleted = True
                
        logger.info("Report loaded: %s (%d entries)", target, len(report.entries))
        return report
    except Exception as exc:
        logger.error("Failed to load report from %s: %s", target, exc)
        return None


def report_path(folder_path: str) -> Path:
    """Return the expected report file path for a folder."""
    return Path(folder_path) / REPORT_FILENAME


def clear_report_files(folder_path: str, recursive: bool = True) -> int:
    """Remove generated report and execution JSON files from a folder tree."""
    root = Path(folder_path)
    if not root.is_dir():
        return 0

    deleted = 0
    file_names = {REPORT_FILENAME, EXECUTED_FILENAME}
    if recursive:
        for path in root.rglob("*"):
            if path.is_file() and path.name in file_names:
                try:
                    path.unlink()
                    deleted += 1
                except OSError as exc:
                    logger.warning("Failed to delete %s: %s", path, exc)
    else:
        for name in file_names:
            path = root / name
            if path.is_file():
                try:
                    path.unlink()
                    deleted += 1
                except OSError as exc:
                    logger.warning("Failed to delete %s: %s", path, exc)

    logger.info("Cleared %d report/executed files from %s", deleted, folder_path)
    return deleted
