"""Video API — streams MP4 video files safely with HTTP range support."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from duplicate_evaluator.config import config

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/video")
async def get_video(path: str) -> FileResponse:
    """
    Stream a video file safely.
    Supports HTTP range requests for timeline scrubbing.
    """
    file_path = Path(path).resolve()
    media_root = Path(config.media.target_path).resolve()

    # Security check: Ensure file is an MP4 and is inside the configured media directory
    if not file_path.exists() or not file_path.is_file():
        logger.warning("Video not found: %s", path)
        raise HTTPException(status_code=404, detail="Video file not found")

    if file_path.suffix.lower() != ".mp4":
        logger.warning("Invalid file format requested for streaming: %s", path)
        raise HTTPException(status_code=400, detail="Only MP4 playback is supported")

    # Ensure the file path is under the media root
    try:
        file_path.relative_to(media_root)
    except ValueError:
        logger.warning("Security alert: Attempted access outside media root: %s", path)
        raise HTTPException(status_code=403, detail="Access denied")

    logger.info("Streaming video: %s", file_path)
    return FileResponse(
        str(file_path),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"}
    )
