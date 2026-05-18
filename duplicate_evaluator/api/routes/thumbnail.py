"""Thumbnail API — NoOp route (returns 204 No Content for now)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter()


@router.get("/thumbnail")
async def get_thumbnail(path: str = "") -> Response:
    """
    NoOp thumbnail endpoint.

    When thumbnails are enabled, this will stream the cached thumbnail image.
    For now it always returns 204 No Content.
    """
    return Response(status_code=204)
