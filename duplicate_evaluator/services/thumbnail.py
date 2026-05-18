"""Thumbnail service — NoOp implementation (disabled for now)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_thumbnail_path(mp4_path: str, cache_dir: str = ".thumbnails") -> Optional[str]:
    """
    NoOp thumbnail retrieval.

    When thumbnails are enabled in future, this will:
    1. Check if a cached thumbnail already exists.
    2. If not, extract a frame from the MP4 via ffmpeg.
    3. Return the path to the thumbnail image.

    For now, always returns None.
    """
    logger.debug("thumbnail.get_thumbnail_path called (NoOp) for: %s", mp4_path)
    return None


async def get_thumbnail_path_async(mp4_path: str, cache_dir: str = ".thumbnails") -> Optional[str]:
    """Async NoOp — see get_thumbnail_path."""
    return None
