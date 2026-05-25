"""Report API — load and update cached report for a folder."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from duplicate_evaluator.models.file_entry import ActionType
from duplicate_evaluator.services.reporter import clear_report_files, load_report, save_report

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/report")
async def get_report(folder_path: str) -> JSONResponse:
    """
    Load a cached _report.json for the given folder path.

    Query param: ?folder_path=<url-encoded-path>
    """
    logger.info("GET /api/report?folder_path=%s", folder_path)
    report = load_report(folder_path)
    if report is None:
        raise HTTPException(status_code=404, detail="No report found for this folder. Run a scan first.")
    return JSONResponse(report.model_dump(mode="json"))


class UpdateActionItem(BaseModel):
    path: str
    action: ActionType


class UpdateReportActionsRequest(BaseModel):
    folder_path: str
    actions: list[UpdateActionItem]


@router.post("/report/actions")
async def update_report_actions(req: UpdateReportActionsRequest) -> JSONResponse:
    """
    Update user actions for specific files within a cached folder report.
    """
    logger.info("POST /api/report/actions for %s (%d actions)", req.folder_path, len(req.actions))
    report = load_report(req.folder_path)
    if report is None:
        raise HTTPException(status_code=404, detail="No report found for this folder.")

    # Build action map for fast lookup
    action_map = {item.path: item.action for item in req.actions}

    updated_count = 0
    for entry in report.entries:
        if entry.file.path in action_map:
            entry.suggested_action = action_map[entry.file.path]
            updated_count += 1

    if updated_count > 0:
        save_report(report)

    return JSONResponse({
        "status": "success",
        "updated_count": updated_count,
        "folder_path": req.folder_path
    })


class ClearReportRequest(BaseModel):
    folder_paths: list[str]
    recursive: bool = True


@router.post("/report/clear")
async def clear_reports(req: ClearReportRequest) -> JSONResponse:
    """Clear generated report and execution result JSON files under one or more folders."""
    logger.info("POST /api/report/clear — %d folders, recursive=%s", len(req.folder_paths), req.recursive)
    results = []

    for folder_path in req.folder_paths:
        folder = Path(folder_path)
        if not folder.is_dir():
            raise HTTPException(status_code=404, detail=f"Folder path not found: {folder_path}")

        deleted = clear_report_files(folder_path, recursive=req.recursive)
        results.append({"folder_path": folder_path, "deleted": deleted})

    total_deleted = sum(item["deleted"] for item in results)
    return JSONResponse({
        "status": "success",
        "total_deleted": total_deleted,
        "results": results,
    })
