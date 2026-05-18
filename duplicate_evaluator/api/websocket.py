"""WebSocket endpoint — streams real-time agent progress."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from duplicate_evaluator.api.routes.scan import _jobs

router = APIRouter()
logger = logging.getLogger(__name__)

POLL_INTERVAL = 0.5  # seconds


@router.websocket("/ws/progress/{job_id}")
async def scan_progress(websocket: WebSocket, job_id: str) -> None:
    """
    Stream progress messages for a running scan job.

    Sends JSON messages as the agent progresses:
      {"type": "progress", "messages": [...]}
      {"type": "done", "status": "done"|"error", "error": "..."}
    """
    await websocket.accept()
    logger.info("WebSocket connected for job %s", job_id)

    seen_count = 0
    try:
        while True:
            job = _jobs.get(job_id)
            if not job:
                await websocket.send_json({"type": "error", "error": "Job not found"})
                break

            messages = job.get("messages", [])
            new_messages = messages[seen_count:]
            if new_messages:
                await websocket.send_json({"type": "progress", "messages": new_messages})
                seen_count += len(new_messages)

            status = job.get("status", "pending")
            if status in ("done", "error"):
                await websocket.send_json({
                    "type": "done",
                    "status": status,
                    "error": job.get("error"),
                    "report_path": job.get("report_path"),
                })
                break

            await asyncio.sleep(POLL_INTERVAL)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for job %s", job_id)
    except Exception as exc:
        logger.error("WebSocket error for job %s: %s", job_id, exc)
        try:
            await websocket.send_json({"type": "error", "error": str(exc)})
        except Exception:
            pass
