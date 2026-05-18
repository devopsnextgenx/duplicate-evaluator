"""LangGraph agent state definition."""

from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict

from duplicate_evaluator.models.file_entry import (
    AnalysisMode,
    FileEntry,
    FolderReport,
    LLMFileResult,
    QualityTier,
)


class AgentState(TypedDict):
    """Shared state flowing through the LangGraph agent graph."""

    # Inputs
    mode: AnalysisMode
    folder_path: str          # primary folder being analyzed
    language: str
    quality: Optional[QualityTier]
    actress: str

    # Computed during scan
    file_entries: list[FileEntry]
    # For cross-quality mode: entries grouped by tier
    cross_quality_entries: dict[str, list[FileEntry]]  # tier -> entries

    # LLM processing
    batches: list[list[str]]           # file name batches for LLM
    llm_results: list[LLMFileResult]   # accumulated across all batches

    # Output
    report: Optional[FolderReport]
    error: Optional[str]
    progress_messages: list[str]       # streaming status updates
