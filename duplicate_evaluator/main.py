"""FastAPI application factory and CLI entrypoint."""

from __future__ import annotations

import logging
from pathlib import Path

import click
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from duplicate_evaluator.config import config, setup_logging
from duplicate_evaluator.api.routes import tree, scan, report, execute, thumbnail, video
from duplicate_evaluator.api.websocket import router as ws_router

# Setup logging first
setup_logging(config.logging)
logger = logging.getLogger(__name__)

# Web static files directory
WEB_DIR = Path(__file__).parent / "web"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Duplicate Evaluator",
        description="Media duplicate detection with local LLM agent",
        version="0.1.0",
    )

    # API routes
    app.include_router(tree.router, prefix="/api", tags=["tree"])
    app.include_router(scan.router, prefix="/api", tags=["scan"])
    app.include_router(report.router, prefix="/api", tags=["report"])
    app.include_router(execute.router, prefix="/api", tags=["execute"])
    app.include_router(thumbnail.router, prefix="/api", tags=["thumbnail"])
    app.include_router(video.router, prefix="/api", tags=["video"])
    app.include_router(ws_router, tags=["websocket"])

    # Serve static web assets
    if WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index() -> FileResponse:
        return FileResponse(str(WEB_DIR / "index.html"))

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "version": "0.1.0",
            "media_root": config.media.target_path,
            "llm_provider": config.llm.provider,
            "llm_model": config.llm.model,
        }

    logger.info(
        "App created — media_root=%s provider=%s model=%s",
        config.media.target_path,
        config.llm.provider,
        config.llm.model,
    )
    return app


app = create_app()


@click.command()
@click.option("--host", default=None, help="Override server host from config")
@click.option("--port", default=None, type=int, help="Override server port from config")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload (dev mode)")
def cli(host: str | None, port: int | None, reload: bool) -> None:
    """Start the Duplicate Evaluator web server."""
    _host = host or config.server.host
    _port = port or config.server.port
    logger.info("Starting Duplicate Evaluator on http://%s:%d", _host, _port)
    uvicorn.run(
        "duplicate_evaluator.main:app",
        host=_host,
        port=_port,
        reload=reload,
        log_level=config.logging.level.lower(),
    )


if __name__ == "__main__":
    cli()
