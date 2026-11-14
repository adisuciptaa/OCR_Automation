"""Immutable application-level contracts for background document jobs.

These models are transport objects between the Presentation, Application, and
Feature layers. They deliberately contain no worker, persistence, or UI logic.
"""
from __future__ import annotations

import math
from collections.abc import Mapping as MappingABC
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping


def _freeze(value: object) -> object:
    """Copy and recursively freeze JSON-like contract payload values."""
    if isinstance(value, MappingABC):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return deepcopy(value)


@dataclass(frozen=True, slots=True)
class JobRequest:
    """Validated request submitted to one registered feature workflow."""

    job_id: str
    feature_id: str
    input_paths: tuple[str, ...]
    output_path: str
    configuration: Mapping[str, object]
    requested_by: str
    correlation_id: str

    def __post_init__(self) -> None:
        for name in ("job_id", "feature_id", "output_path", "requested_by", "correlation_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        paths = tuple(self.input_paths)
        if not paths or any(not isinstance(path, str) or not path.strip() for path in paths):
            raise ValueError("input_paths must contain at least one non-empty path.")
        object.__setattr__(self, "input_paths", paths)
        if not isinstance(self.configuration, Mapping):
            raise TypeError("configuration must be a mapping.")
        object.__setattr__(self, "configuration", _freeze(self.configuration))


@dataclass(frozen=True, slots=True)
class JobProgress:
    """Safe progress projection; it must not carry OCR text or extracted values."""

    job_id: str
    stage: str
    current_file: str | None
    completed_files: int
    total_files: int
    message_code: str
    message: str

    def __post_init__(self) -> None:
        if not self.job_id.strip() or not self.stage.strip() or not self.message_code.strip():
            raise ValueError("job_id, stage, and message_code must be non-empty.")
        if self.completed_files < 0 or self.total_files < 0:
            raise ValueError("Job progress counts cannot be negative.")
        if self.completed_files > self.total_files:
            raise ValueError("completed_files cannot exceed total_files.")


@dataclass(frozen=True, slots=True)
class FileResult:
    """Per-input result using feature-neutral field identifiers and values."""

    source_path: str
    status: Literal["success", "failed", "review", "skipped"]
    extracted_fields: Mapping[str, object]
    confidence: Mapping[str, float]
    warnings: tuple[str, ...] = ()
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not self.source_path.strip():
            raise ValueError("source_path must be a non-empty string.")
        if self.status not in {"success", "failed", "review", "skipped"}:
            raise ValueError("Unsupported file result status.")
        if self.status == "failed" and not self.error_code:
            raise ValueError("A failed file result must include an error_code.")
        if self.status != "failed" and self.error_code is not None:
            raise ValueError("error_code is only valid for a failed file result.")
        confidence = dict(self.confidence)
        if any(not math.isfinite(value) for value in confidence.values()):
            raise ValueError("Confidence values must be finite engine scores.")
        object.__setattr__(self, "extracted_fields", _freeze(self.extracted_fields))
        object.__setattr__(self, "confidence", MappingProxyType(confidence))
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass(frozen=True, slots=True)
class JobResult:
    """Aggregate result for one feature execution request."""

    job_id: str
    status: Literal["completed", "completed_with_warnings", "failed", "cancelled"]
    total_files: int
    successful_files: int
    failed_files: int
    review_files: int
    results: tuple[FileResult, ...]
    output_path: str | None

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("job_id must be a non-empty string.")
        counts = (self.total_files, self.successful_files, self.failed_files, self.review_files)
        if any(value < 0 for value in counts):
            raise ValueError("Job result counts cannot be negative.")
        results = tuple(self.results)
        if self.total_files != len(results):
            raise ValueError("total_files must equal the number of per-file results.")
        expected = {
            "successful_files": sum(item.status == "success" for item in results),
            "failed_files": sum(item.status == "failed" for item in results),
            "review_files": sum(item.status == "review" for item in results),
        }
        for name, value in expected.items():
            if getattr(self, name) != value:
                raise ValueError(f"{name} does not match per-file results.")
        if self.status == "failed" and self.successful_files:
            raise ValueError("A failed job cannot report successful files.")
        object.__setattr__(self, "results", results)
