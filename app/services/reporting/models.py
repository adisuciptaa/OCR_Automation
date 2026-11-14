"""Structured, document-content-free reporting models."""
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True, slots=True)
class ReportFileOutcome:
    source_name: str
    status: Literal["success", "failed", "review", "skipped"]
    error_code: str | None = None
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class ProcessingReport:
    job_id: str
    feature_id: str
    created_at: str
    outcomes: tuple[ReportFileOutcome, ...]
    summary: tuple[tuple[str, int], ...]
