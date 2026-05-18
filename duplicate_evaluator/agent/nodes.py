"""LangGraph node functions for the duplicate evaluator agent."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from duplicate_evaluator.agent.llm_client import create_llm_client
from duplicate_evaluator.agent.prompts import (
    CROSS_QUALITY_SYSTEM,
    CROSS_QUALITY_USER,
    WITHIN_FOLDER_SYSTEM,
    WITHIN_FOLDER_USER,
)
from duplicate_evaluator.config import config
from duplicate_evaluator.models.file_entry import (
    ActionType,
    AnalysisMode,
    FileEntry,
    FolderReport,
    LLMBatchResponse,
    LLMFileResult,
    QualityTier,
    ReportEntry,
)
from duplicate_evaluator.models.state import AgentState
from duplicate_evaluator.services.scanner import scan_actress_folder, scan_cross_quality

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node: scan
# ---------------------------------------------------------------------------

def scan_node(state: AgentState) -> dict:
    """Walk the target folder and collect FileEntry objects."""
    logger.info("scan_node: scanning folder=%s mode=%s", state["folder_path"], state["mode"])
    messages = list(state.get("progress_messages", []))

    try:
        if state["mode"] == AnalysisMode.CROSS_QUALITY:
            cross_entries = scan_cross_quality(
                language=state["language"],
                actress=state["actress"],
                media_root=config.media.target_path,
            )
            all_entries: list[FileEntry] = []
            for tier_entries in cross_entries.values():
                all_entries.extend(tier_entries)
            messages.append(
                f"✅ Scanned {len(all_entries)} files across quality tiers for {state['actress']}"
            )
            return {
                "file_entries": all_entries,
                "cross_quality_entries": cross_entries,
                "progress_messages": messages,
            }
        else:
            entries = scan_actress_folder(state["folder_path"])
            messages.append(f"✅ Scanned {len(entries)} files in {state['folder_path']}")
            return {
                "file_entries": entries,
                "cross_quality_entries": {},
                "progress_messages": messages,
            }
    except Exception as exc:
        logger.exception("scan_node failed: %s", exc)
        return {"error": str(exc), "progress_messages": messages}


# ---------------------------------------------------------------------------
# Node: batch
# ---------------------------------------------------------------------------

def batch_node(state: AgentState) -> dict:
    """Split file names into LLM-sized batches."""
    if state.get("error"):
        return {}

    batch_size = config.llm.batch_size
    filenames = [e.filename for e in state["file_entries"]]

    batches: list[list[str]] = [
        filenames[i : i + batch_size] for i in range(0, len(filenames), batch_size)
    ]
    messages = list(state.get("progress_messages", []))
    messages.append(f"📦 Prepared {len(batches)} batch(es) of up to {batch_size} files")
    logger.debug("batch_node: %d batches", len(batches))
    return {"batches": batches, "progress_messages": messages}


# ---------------------------------------------------------------------------
# Node: llm (within-folder)
# ---------------------------------------------------------------------------

def llm_node(state: AgentState) -> dict:
    """Send file name batches to LLM and collect structured results."""
    if state.get("error"):
        return {}

    llm = create_llm_client(config.llm)
    all_results: list[LLMFileResult] = list(state.get("llm_results", []))
    messages = list(state.get("progress_messages", []))

    for idx, batch in enumerate(state.get("batches", []), 1):
        logger.info("llm_node: processing batch %d/%d (%d files)", idx, len(state["batches"]), len(batch))
        messages.append(f"🤖 LLM analysing batch {idx}/{len(state['batches'])} ({len(batch)} files)…")

        filenames_text = "\n".join(f"- {fn}" for fn in batch)
        user_msg = WITHIN_FOLDER_USER.format(filenames=filenames_text)

        try:
            response = llm.invoke(
                [SystemMessage(content=WITHIN_FOLDER_SYSTEM), HumanMessage(content=user_msg)]
            )
            raw = response.content if hasattr(response, "content") else str(response)
            batch_result = _parse_llm_response(raw)
            all_results.extend(batch_result.files)
            messages.append(f"✅ Batch {idx}: {len(batch_result.files)} findings")
        except Exception as exc:
            logger.error("llm_node batch %d failed: %s", idx, exc)
            messages.append(f"⚠️ Batch {idx} failed: {exc}")

    return {"llm_results": all_results, "progress_messages": messages}


# ---------------------------------------------------------------------------
# Node: cross_quality_llm
# ---------------------------------------------------------------------------

def cross_quality_llm_node(state: AgentState) -> dict:
    """Send cross-quality file lists to LLM as a single prompt."""
    if state.get("error"):
        return {}

    llm = create_llm_client(config.llm)
    messages = list(state.get("progress_messages", []))
    cq = state.get("cross_quality_entries", {})

    def _fmt(tier: str) -> str:
        entries = cq.get(tier, [])
        if not entries:
            return "(none)"
        return "\n".join(f"- {e.filename}" for e in entries)

    user_msg = CROSS_QUALITY_USER.format(
        actress=state["actress"],
        language=state["language"],
        xhd_files=_fmt("xhd"),
        hd_files=_fmt("hd"),
        sd_files=_fmt("sd"),
    )

    messages.append(f"🤖 LLM analysing cross-quality files for {state['actress']}…")
    try:
        response = llm.invoke(
            [SystemMessage(content=CROSS_QUALITY_SYSTEM), HumanMessage(content=user_msg)]
        )
        raw = response.content if hasattr(response, "content") else str(response)
        result = _parse_llm_response(raw)
        messages.append(f"✅ Cross-quality analysis: {len(result.files)} findings")
        return {"llm_results": result.files, "progress_messages": messages}
    except Exception as exc:
        logger.error("cross_quality_llm_node failed: %s", exc)
        messages.append(f"⚠️ Cross-quality LLM failed: {exc}")
        return {"llm_results": [], "progress_messages": messages}


# ---------------------------------------------------------------------------
# Node: merge
# ---------------------------------------------------------------------------

def merge_node(state: AgentState) -> dict:
    """Merge LLM results with file entries into a FolderReport."""
    if state.get("error"):
        return {}

    messages = list(state.get("progress_messages", []))

    # Build a lookup of LLM results by filename
    llm_map: dict[str, LLMFileResult] = {r.filename: r for r in state.get("llm_results", [])}

    entries: list[ReportEntry] = []
    for fe in state.get("file_entries", []):
        llm_r = llm_map.get(fe.filename)
        if llm_r:
            is_dup = llm_r.is_duplicate
            needs_rename = llm_r.needs_rename
            confidence = llm_r.confidence
            reason = llm_r.reason
        else:
            is_dup = False
            needs_rename = False
            confidence = 0.0
            reason = ""

        # Determine suggested action
        if is_dup:
            suggested = ActionType.DELETE
        elif needs_rename:
            suggested = ActionType.RENAME
        else:
            suggested = ActionType.KEEP

        entries.append(
            ReportEntry(
                file=fe,
                is_duplicate=is_dup,
                needs_rename=needs_rename,
                confidence=confidence,
                reason=reason,
                suggested_action=suggested,
            )
        )

    report = FolderReport(
        folder_path=state["folder_path"],
        language=state.get("language", ""),
        quality=state.get("quality"),
        actress=state.get("actress", ""),
        mode=state["mode"],
        entries=entries,
        llm_model=config.llm.model,
        total_files_scanned=len(state.get("file_entries", [])),
    )

    messages.append(
        f"📊 Report built: {report.duplicate_count} duplicates, {report.rename_count} to rename"
    )
    logger.info(
        "merge_node: report for %s — %d duplicates, %d renames",
        state["folder_path"],
        report.duplicate_count,
        report.rename_count,
    )
    return {"report": report, "progress_messages": messages}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_llm_response(raw: str) -> LLMBatchResponse:
    """Extract and parse JSON from LLM response, tolerating minor formatting issues."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip().rstrip("`").strip()

    # Find first { ... } block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        logger.warning("No JSON object found in LLM response. Raw: %s", raw[:200])
        return LLMBatchResponse(files=[])

    try:
        data = json.loads(match.group())
        # Normalize keys: allow both camelCase and snake_case from LLM
        normalised_files = []
        for f in data.get("files", []):
            normalised_files.append(
                LLMFileResult(
                    filename=f.get("filename", ""),
                    is_duplicate=f.get("isDuplicate", f.get("is_duplicate", False)),
                    needs_rename=f.get("needsRename", f.get("needs_rename", False)),
                    confidence=float(f.get("confidence", 0.0)),
                    reason=f.get("reason", ""),
                )
            )
        return LLMBatchResponse(files=normalised_files)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("JSON parse error: %s | raw snippet: %s", exc, cleaned[:300])
        return LLMBatchResponse(files=[])
