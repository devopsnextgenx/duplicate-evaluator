"""Execute API — dry-run and real delete/rename operations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from duplicate_evaluator.models.file_entry import ActionType, FileAction
from duplicate_evaluator.services.executor import execute_actions

router = APIRouter()
logger = logging.getLogger(__name__)


class ExecuteActionItem(BaseModel):
    filename: str
    path: str
    action: ActionType


class ExecuteRequest(BaseModel):
    actions: list[ExecuteActionItem]
    dry_run: bool = True


@router.post("/execute")
async def execute(req: ExecuteRequest) -> JSONResponse:
    """
    Execute (or simulate) delete/rename actions.

    Set dry_run=false for real execution.
    Returns terminal-style log lines.
    """
    logger.info(
        "POST /api/execute — %d actions, dry_run=%s", len(req.actions), req.dry_run
    )
    file_actions = [
        FileAction(filename=a.filename, path=a.path, action=a.action)
        for a in req.actions
    ]
    lines = execute_actions(file_actions, dry_run=req.dry_run)
    return JSONResponse({"lines": lines, "dry_run": req.dry_run})


class MarkExecutedRequest(BaseModel):
    folder_path: str


@router.post("/execute/mark-executed")
async def mark_executed(req: MarkExecutedRequest) -> JSONResponse:
    """
    Manually mark a folder as executed by writing _executed.json.
    """
    logger.info("POST /api/execute/mark-executed for %s", req.folder_path)
    actress_dir = Path(req.folder_path)
    if not actress_dir.is_dir():
        raise HTTPException(status_code=404, detail="Folder path not found")

    import json
    from datetime import datetime, timezone
    executed_info = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "manual": True,
        "actions": []
    }
    executed_file = actress_dir / "_executed.json"
    try:
        executed_file.write_text(json.dumps(executed_info, indent=2), encoding="utf-8")
        logger.info("Manual executed marker written to %s", executed_file)
        return JSONResponse({"status": "success", "message": "Folder marked as executed manually."})
    except Exception as exc:
        logger.error("Failed to write _executed.json: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to write executed marker: {exc}")
