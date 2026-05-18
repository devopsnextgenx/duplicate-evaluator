"""OpenAI-compatible LLM client factory for Ollama, LM Studio, and llama.cpp."""

from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI

from duplicate_evaluator.config import LLMConfig

logger = logging.getLogger(__name__)

# Default URLs per provider
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
    },
    "lmstudio": {
        "base_url": "http://localhost:1234/v1",
        "api_key": "lm-studio",
    },
    "llamacpp": {
        "base_url": "http://localhost:8000/v1",
        "api_key": "sk-no-key-required",
    },
}


def create_llm_client(cfg: LLMConfig) -> ChatOpenAI:
    """
    Create a LangChain ChatOpenAI client pointing at a local LLM server.

    All three backends (Ollama, LM Studio, llama.cpp) expose an
    OpenAI-compatible REST API, so the same client class works for all.
    """
    defaults = PROVIDER_DEFAULTS.get(cfg.provider, {})
    base_url = cfg.base_url or defaults.get("base_url", "http://localhost:11434/v1")
    api_key = cfg.api_key or defaults.get("api_key", "dummy")

    logger.info(
        "Initialising LLM client: provider=%s model=%s url=%s",
        cfg.provider,
        cfg.model,
        base_url,
    )

    return ChatOpenAI(
        model=cfg.model,
        base_url=base_url,
        api_key=api_key,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        streaming=False,  # We use structured output; streaming not needed here
    )
