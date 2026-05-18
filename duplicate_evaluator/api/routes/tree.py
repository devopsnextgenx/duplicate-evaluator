"""Tree API — returns the full folder tree as JSON."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from duplicate_evaluator.config import config
from duplicate_evaluator.services.scanner import build_folder_tree

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/tree")
async def get_tree() -> JSONResponse:
    """Return the full media folder tree structure."""
    logger.info("GET /api/tree — root=%s", config.media.target_path)
    tree = build_folder_tree(config.media.target_path)
    return JSONResponse(content=tree)
