"""Pydantic models for file entries, LLM responses, and folder reports."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class QualityTier(str, Enum):
    XHD = "xhd"
    HD = "hd"
    SD = "sd"
    UNKNOWN = "unknown"


QUALITY_RESOLUTION_MAP: dict[QualityTier, list[int]] = {
    QualityTier.XHD: [2160, 1440],
    QualityTier.HD: [1080, 720],
    QualityTier.SD: [],  # below 720
}


class FileEntry(BaseModel):
    """Represents a single MP4 file discovered during scan."""

    filename: str
    path: str  # absolute path
    size_bytes: int = 0
    language: str = ""
    quality: QualityTier = QualityTier.UNKNOWN
    actress: str = ""
    thumbnail_path: Optional[str] = None  # NoOp for now

    @computed_field  # type: ignore[misc]
    @property
    def size_human(self) -> str:
        """Human-readable file size."""
        size = self.size_bytes
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


class LLMFileResult(BaseModel):
    """Per-file result from LLM analysis."""

    filename: str
    is_duplicate: bool = False
    needs_rename: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""


class LLMBatchResponse(BaseModel):
    """Full structured response from LLM for a batch of files."""

    files: list[LLMFileResult] = Field(default_factory=list)


class ActionType(str, Enum):
    DELETE = "delete"
    RENAME = "rename"
    KEEP = "keep"


class FileAction(BaseModel):
    """User-selected action for a file."""

    filename: str
    path: str
    action: ActionType


class ReportEntry(BaseModel):
    """Combined entry in the folder report (file info + LLM result)."""

    file: FileEntry
    is_duplicate: bool = False
    needs_rename: bool = False
    confidence: float = 0.0
    reason: str = ""
    suggested_action: ActionType = ActionType.KEEP
    deleted: bool = False

    @computed_field  # type: ignore[misc]
    @property
    def suggested_rename(self) -> Optional[str]:
        """Pre-computed rename suggestion."""
        if not self.needs_rename:
            return None
        return _clean_filename(self.file.filename)


def _clean_filename(name: str) -> str:
    """Apply rename rules: underscore→space, camelCase→space, strip extension."""
    stem = Path(name).stem
    suffix = Path(name).suffix

    # Replace underscores with spaces
    result = stem.replace("_", " ")

    # Insert space before uppercase letter preceded by lowercase (camelCase split)
    import re
    result = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", result)

    # Collapse multiple spaces, strip
    result = re.sub(r" +", " ", result).strip()

    return result + suffix


class AnalysisMode(str, Enum):
    WITHIN_FOLDER = "within_folder"
    CROSS_QUALITY = "cross_quality"
    CROSS_LANGUAGE = "cross_language"  # reserved / in-progress


class FolderReport(BaseModel):
    """Complete analysis report for a folder or actress + quality combo."""

    folder_path: str
    language: str = ""
    quality: Optional[QualityTier] = None
    actress: str = ""
    mode: AnalysisMode = AnalysisMode.WITHIN_FOLDER
    entries: list[ReportEntry] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    llm_model: str = ""
    total_files_scanned: int = 0
    error: Optional[str] = None

    @computed_field  # type: ignore[misc]
    @property
    def duplicate_count(self) -> int:
        return sum(1 for e in self.entries if e.is_duplicate)

    @computed_field  # type: ignore[misc]
    @property
    def rename_count(self) -> int:
        return sum(1 for e in self.entries if e.needs_rename)
