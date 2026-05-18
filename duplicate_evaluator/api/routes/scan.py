"""Scan API — triggers the LangGraph agent for a folder."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from duplicate_evaluator.agent.graph import agent_graph
from duplicate_evaluator.config import config
from duplicate_evaluator.models.file_entry import AnalysisMode, QualityTier
from duplicate_evaluator.services.reporter import save_report

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory job registry (sufficient for single-user local app)
_jobs: dict[str, dict] = {}


class ScanRequest(BaseModel):
    folder_path: str
    mode: AnalysisMode = AnalysisMode.WITHIN_FOLDER
    language: Optional[str] = ""
    quality: Optional[QualityTier] = None
    actress: Optional[str] = ""


@router.post("/scan")
async def start_scan(req: ScanRequest, background_tasks: BackgroundTasks) -> JSONResponse:
    """Start an agent scan job in the background. Returns job_id immediately."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "messages": [], "error": None}

    background_tasks.add_task(_run_scan, job_id, req)
    logger.info("Scan job %s created: folder=%s mode=%s", job_id, req.folder_path, req.mode)
    return JSONResponse({"job_id": job_id, "status": "pending"})


from pathlib import Path

@router.post("/rescan")
async def start_rescan(req: ScanRequest, background_tasks: BackgroundTasks) -> JSONResponse:
    """Delete stale reports and run a fresh scan."""
    folder = Path(req.folder_path)
    if folder.is_dir():
        for item in ("_report.json", "_executed.json"):
            p = folder / item
            if p.exists():
                try:
                    p.unlink()
                    logger.info("Deleted stale file: %s", p)
                except Exception as e:
                    logger.warning("Could not delete stale file %s: %s", p, e)

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "messages": [], "error": None}

    background_tasks.add_task(_run_scan, job_id, req)
    logger.info("Rescan job %s created: folder=%s mode=%s", job_id, req.folder_path, req.mode)
    return JSONResponse({"job_id": job_id, "status": "pending"})


@router.get("/scan/{job_id}")
async def get_scan_status(job_id: str) -> JSONResponse:
    """Poll scan job status and progress messages."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(job)


async def _run_scan(job_id: str, req: ScanRequest) -> None:
    """Background task: run the agent graph and save the report."""
    _jobs[job_id]["status"] = "running"
    try:
        initial_state = {
            "mode": req.mode,
            "folder_path": req.folder_path,
            "language": req.language or "",
            "quality": req.quality,
            "actress": req.actress or "",
            "file_entries": [],
            "cross_quality_entries": {},
            "batches": [],
            "llm_results": [],
            "report": None,
            "error": None,
            "progress_messages": [],
        }

        # Run synchronously in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        final_state = await loop.run_in_executor(
            None, lambda: agent_graph.invoke(initial_state)
        )

        if final_state.get("error"):
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = final_state["error"]
            logger.error("Scan job %s failed: %s", job_id, final_state["error"])
        else:
            report = final_state.get("report")
            if report:
                save_report(report)
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["report_path"] = str(report.folder_path) if report else None

        _jobs[job_id]["messages"] = final_state.get("progress_messages", [])

    except Exception as exc:
        logger.exception("Scan job %s crashed: %s", job_id, exc)
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(exc)
