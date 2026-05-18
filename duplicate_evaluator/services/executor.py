"""Executor service — dry-run and real file delete/rename operations."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Literal

from duplicate_evaluator.models.file_entry import FileAction, ActionType

logger = logging.getLogger(__name__)


def _compute_rename(path: Path) -> Path:
    """
    Compute the renamed path applying:
    1. Replace underscores with spaces in the stem.
    2. Insert space between camelCase transitions (lowercase→uppercase).
    3. Collapse multiple spaces, strip leading/trailing spaces.
    """
    stem = path.stem
    suffix = path.suffix

    # Underscores → spaces
    result = stem.replace("_", " ")
    result = stem.replace("-", " ")

    # camelCase split: insert space before uppercase preceded by lowercase
    result = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", result)

    # Collapse multiple spaces
    result = re.sub(r" +", " ", result).strip()

    return path.parent / (result + suffix)


def execute_actions(
    actions: list[FileAction],
    dry_run: bool = True,
) -> list[str]:
    """
    Execute (or simulate) a list of file actions.

    Returns a list of terminal-style log lines for display in the UI.
    """
    log_lines: list[str] = []

    mode_label = "[DRY RUN] " if dry_run else ""

    for action in actions:
        path = Path(action.path)

        if action.action == ActionType.KEEP:
            continue  # No-op

        if not path.exists():
            line = f"⚠️  {mode_label}SKIP — file not found: {path}"
            log_lines.append(line)
            logger.warning("execute: file not found: %s", path)
            continue

        if action.action == ActionType.DELETE:
            log_lines.append(f"🗑️  {mode_label}DELETE: {path}")
            logger.info("execute: DELETE %s (dry_run=%s)", path, dry_run)
            if not dry_run:
                try:
                    path.unlink()
                    log_lines.append(f"   ✅ Deleted: {path.name}")
                except OSError as exc:
                    msg = f"   ❌ Error deleting {path.name}: {exc}"
                    log_lines.append(msg)
                    logger.error("execute: delete failed: %s", exc)

        elif action.action == ActionType.RENAME:
            new_path = _compute_rename(path)
            log_lines.append(f"✏️  {mode_label}RENAME: {path.name}")
            log_lines.append(f"           → {new_path.name}")
            logger.info("execute: RENAME %s → %s (dry_run=%s)", path, new_path, dry_run)

            if not dry_run:
                if new_path.exists():
                    msg = f"   ❌ Skip — target already exists: {new_path.name}"
                    log_lines.append(msg)
                    logger.warning("execute: rename target exists: %s", new_path)
                else:
                    try:
                        path.rename(new_path)
                        log_lines.append(f"   ✅ Renamed successfully")
                    except OSError as exc:
                        msg = f"   ❌ Error renaming: {exc}"
                        log_lines.append(msg)
                        logger.error("execute: rename failed: %s", exc)

    summary = (
        f"\n{'─' * 50}\n"
        f"{'DRY RUN ' if dry_run else ''}COMPLETE — {len(actions)} action(s) processed"
    )
    log_lines.append(summary)

    if not dry_run and actions:
        try:
            first_path = Path(actions[0].path)
            actress_dir = first_path.parent
            if actress_dir.is_dir():
                import json
                from datetime import datetime, timezone
                executed_info = {
                    "executed_at": datetime.now(timezone.utc).isoformat(),
                    "actions": [{"filename": a.filename, "path": a.path, "action": str(a.action)} for a in actions]
                }
                executed_file = actress_dir / "_executed.json"
                executed_file.write_text(json.dumps(executed_info, indent=2), encoding="utf-8")
                logger.info("Executed info written to %s", executed_file)
        except Exception as exc:
            logger.error("Failed to write _executed.json: %s", exc)

    return log_lines
