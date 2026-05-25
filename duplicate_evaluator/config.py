"""Application configuration loader using Pydantic-Settings and YAML."""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator
from rich.logging import RichHandler

CONFIG_PATH = Path(os.environ.get("DUPEVAL_CONFIG", "config.yml"))


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8765


class MediaConfig(BaseModel):
    target_path: str = ""

    @field_validator("target_path")
    @classmethod
    def path_must_exist_if_set(cls, v: str) -> str:
        if v and not Path(v).exists():
            raise ValueError(f"target_path does not exist: {v}")
        return v


class LLMConfig(BaseModel):
    provider: Literal["ollama", "lmstudio", "llamacpp"] = "ollama"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    model: str = "llama3.2"
    temperature: float = 0.1
    max_tokens: int = 4096
    batch_size: int = 50


class ThumbnailConfig(BaseModel):
    enabled: bool = False  # NoOp for now


class LoggingConfig(BaseModel):
    level: str = "INFO"
    log_file: str = "logs/app.log"
    max_bytes: int = 10_485_760
    backup_count: int = 5


class AppConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    media: MediaConfig = MediaConfig()
    llm: LLMConfig = LLMConfig()
    thumbnails: ThumbnailConfig = ThumbnailConfig()
    logging: LoggingConfig = LoggingConfig()


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    """Load and validate configuration from YAML file."""
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    # Allow Docker / environment overrides for the media root, server details, and LLM endpoint
    if env_target := os.environ.get("DUPEVAL_TARGET_PATH"):
        raw.setdefault("media", {})["target_path"] = env_target

    if env_host := os.environ.get("DUPEVAL_HOST"):
        raw.setdefault("server", {})["host"] = env_host

    if env_port := os.environ.get("DUPEVAL_PORT"):
        try:
            raw.setdefault("server", {})["port"] = int(env_port)
        except ValueError:
            raise ValueError("DUPEVAL_PORT must be an integer")

    # LLM endpoint: allow direct override via DUPEVAL_LLM_BASE_URL, or construct from host+port
    if env_llm_base_url := os.environ.get("DUPEVAL_LLM_BASE_URL"):
        raw.setdefault("llm", {})["base_url"] = env_llm_base_url
    elif (env_llm_host := os.environ.get("DUPEVAL_LLM_HOST")) and (
        env_llm_port := os.environ.get("DUPEVAL_LLM_PORT")
    ):
        raw.setdefault("llm", {})["base_url"] = f"http://{env_llm_host}:{env_llm_port}/v1"

    return AppConfig.model_validate(raw)


def setup_logging(cfg: LoggingConfig) -> None:
    """Configure rich console logging + rotating file handler."""
    log_path = Path(cfg.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, cfg.level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [
        RichHandler(rich_tracebacks=True, markup=True, show_path=False),
    ]

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=cfg.max_bytes,
        backupCount=cfg.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=handlers,
        force=True,
    )

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "openai", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# Singleton config instance loaded at import time
config: AppConfig = load_config()
