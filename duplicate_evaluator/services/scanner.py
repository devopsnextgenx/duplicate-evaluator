"""Folder tree scanner — walks the media hierarchy and builds FileEntry objects."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from duplicate_evaluator.models.file_entry import FileEntry, QualityTier

logger = logging.getLogger(__name__)

# Recognised quality folder names (case-insensitive)
QUALITY_MAP: dict[str, QualityTier] = {
    "xhd": QualityTier.XHD,
    "hd": QualityTier.HD,
    "sd": QualityTier.SD,
}


def _quality_from_path(path: Path) -> QualityTier:
    """Determine quality tier from a path that contains xhd/hd/sd segment."""
    for part in path.parts:
        q = QUALITY_MAP.get(part.lower())
        if q:
            return q
    return QualityTier.UNKNOWN


def scan_actress_folder(folder_path: str) -> list[FileEntry]:
    """
    Scan a single actress folder and return a list of MP4 FileEntry objects.

    Expected path structure:
        <media_root>/<language>/<quality>/<actress>/
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        logger.warning("scan_actress_folder: path is not a directory: %s", folder_path)
        return []

    # Derive hierarchy from path segments
    parts = folder.parts
    try:
        # Try to detect quality segment
        quality = _quality_from_path(folder)
        actress = folder.name
        # The segment before quality is the language
        for i, part in enumerate(parts):
            if part.lower() in QUALITY_MAP:
                language = parts[i - 1] if i > 0 else ""
                break
        else:
            language = ""
    except Exception:
        quality = QualityTier.UNKNOWN
        actress = folder.name
        language = ""

    entries: list[FileEntry] = []
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.suffix.lower() == ".mp4":
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            entries.append(
                FileEntry(
                    filename=f.name,
                    path=str(f),
                    size_bytes=size,
                    language=language,
                    quality=quality,
                    actress=actress,
                )
            )
    logger.debug("scan_actress_folder: found %d MP4 files in %s", len(entries), folder_path)
    return entries


def scan_cross_quality(
    language: str,
    actress: str,
    media_root: str,
) -> dict[str, list[FileEntry]]:
    """
    Scan the same actress folder across all quality tiers for one language.

    Returns a dict mapping tier name → list[FileEntry].
    """
    root = Path(media_root)
    result: dict[str, list[FileEntry]] = {"xhd": [], "hd": [], "sd": []}

    for tier_name in ("xhd", "hd", "sd"):
        actress_dir = root / language / tier_name / actress
        if actress_dir.is_dir():
            entries = scan_actress_folder(str(actress_dir))
            result[tier_name] = entries
            logger.debug(
                "scan_cross_quality: %s/%s/%s — %d files", language, tier_name, actress, len(entries)
            )
        else:
            logger.debug("scan_cross_quality: not found — %s", actress_dir)

    return result


import os
from concurrent.futures import ThreadPoolExecutor

def _scan_actress_dir(actress_dir: Path, lang_name: str, quality_name: str) -> dict:
    """Helper to scan a single actress directory efficiently."""
    try:
        mp4_count = 0
        has_report = False
        has_executed = False

        # Scan folder using faster os.scandir
        for entry in os.scandir(actress_dir):
            if entry.is_file():
                name_lower = entry.name.lower()
                if name_lower.endswith(".mp4"):
                    mp4_count += 1
                elif name_lower == "_report.json":
                    has_report = True
                elif name_lower == "_executed.json":
                    has_executed = True

        # Determine scan status
        scan_status = "none"
        if has_executed:
            scan_status = "executed"
        elif has_report:
            scan_status = "ai_processed"
            try:
                report_path = actress_dir / "_report.json"
                content = report_path.read_text(encoding="utf-8")
                # If llm_model is empty/null/missing, it's just basic scanned
                if '"llm_model": ""' in content or '"llm_model":null' in content or '"llm_model": ""' in content:
                    scan_status = "scanned"
            except Exception:
                pass

        has_alert = False
        if has_report:
            report_path = actress_dir / "_report.json"
            has_alert = _report_contains_alert(report_path)

        return {
            "name": actress_dir.name,
            "path": str(actress_dir),
            "type": "actress",
            "mp4_count": mp4_count,
            "has_report": has_report,
            "has_alert": has_alert,
            "scan_status": scan_status,
            "language": lang_name,
            "quality": quality_name,
        }
    except Exception as exc:
        logger.error("Error scanning actress dir %s: %s", actress_dir, exc)
        return {
            "name": actress_dir.name,
            "path": str(actress_dir),
            "type": "actress",
            "mp4_count": 0,
            "has_report": False,
            "scan_status": "none",
            "language": lang_name,
            "quality": quality_name,
        }


def _report_contains_alert(report_path: Path) -> bool:
    """Return True if the report contains duplicates or delete suggestions."""
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        for entry in data.get("entries", []):
            if entry.get("is_duplicate"):
                return True
            if entry.get("deleted"):
                return True
            if entry.get("suggested_action") == "delete":
                return True
        return False
    except Exception:
        return False


def build_folder_tree(media_root: str) -> dict:
    """
    Build a nested dict representing the full folder tree.
    Uses ThreadPoolExecutor for extremely fast scanning of actress folders.
    """
    root = Path(media_root)
    if not root.is_dir():
        logger.error("build_folder_tree: media_root does not exist: %s", media_root)
        return {"name": "root", "path": str(root), "type": "root", "children": [], "error": "Path not found"}

    tree: dict = {
        "name": root.name,
        "path": str(root),
        "type": "root",
        "children": [],
    }

    # Collect tasks to parallelize
    tasks = []

    for lang_dir in sorted(root.iterdir()):
        if not lang_dir.is_dir() or lang_dir.name.startswith("."):
            continue

        for quality_dir in sorted(lang_dir.iterdir()):
            if not quality_dir.is_dir() or quality_dir.name.lower() not in QUALITY_MAP:
                continue

            for actress_dir in sorted(quality_dir.iterdir()):
                if not actress_dir.is_dir() or actress_dir.name.startswith("."):
                    continue
                tasks.append((actress_dir, lang_dir.name, quality_dir.name.lower()))

    # Scan actress folders in parallel
    actress_results: dict[tuple[str, str, str], dict] = {}
    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_scan_actress_dir, path, lang, qual): (path, lang, qual)
            for path, lang, qual in tasks
        }
        for future in futures:
            path, lang, qual = futures[future]
            try:
                result = future.result()
                actress_results[(str(path), lang, qual)] = result
            except Exception as exc:
                logger.error("Failed executing task for %s: %s", path, exc)

    # Assemble the tree
    for lang_dir in sorted(root.iterdir()):
        if not lang_dir.is_dir() or lang_dir.name.startswith("."):
            continue

        lang_node: dict = {
            "name": lang_dir.name,
            "path": str(lang_dir),
            "type": "language",
            "children": [],
        }

        for quality_dir in sorted(lang_dir.iterdir()):
            if not quality_dir.is_dir() or quality_dir.name.lower() not in QUALITY_MAP:
                continue

            quality_node: dict = {
                "name": quality_dir.name,
                "path": str(quality_dir),
                "type": "quality",
                "tier": quality_dir.name.lower(),
                "children": [],
            }

            for actress_dir in sorted(quality_dir.iterdir()):
                if not actress_dir.is_dir() or actress_dir.name.startswith("."):
                    continue

                res = actress_results.get((str(actress_dir), lang_dir.name, quality_dir.name.lower()))
                if res:
                    quality_node["children"].append(res)

            lang_node["children"].append(quality_node)

        tree["children"].append(lang_node)

    return tree

