"""Engine-neutral Excel request and response models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class WorkbookDescriptor:
    path: str
    worksheets: tuple[str, ...]
    file_format: str
    has_macros: bool = False
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExcelMapping:
    """Feature-owned mapping values consumed by the generic Excel service."""

    worksheet: str
    header_row: int | None
    data_start_row: int
    source_key_column: str
    target_column: str
    key_type: Literal["text", "number"] = "text"
    normalization_profile: str = "exact"
    duplicate_policy: Literal["reject", "review", "first", "all"] = "review"
    unmatched_policy: Literal["report", "skip", "fail"] = "report"
    overwrite_policy: Literal["empty_only", "overwrite", "review"] = "empty_only"


@dataclass(frozen=True, slots=True)
class ExcelReadRequest:
    path: str
    worksheet: str
    header_row: int | None
    data_start_row: int
    columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExcelRecord:
    row_number: int
    values: tuple[tuple[str, object], ...]


@dataclass(frozen=True, slots=True)
class ExcelReadResult:
    records: tuple[ExcelRecord, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExcelWriteRequest:
    source_path: str
    destination_path: str
    worksheet: str
    records: tuple[ExcelRecord, ...]
    overwrite_policy: Literal["empty_only", "overwrite", "review"] = "empty_only"
    mapping: ExcelMapping | None = None


@dataclass(frozen=True, slots=True)
class ExcelWriteResult:
    output_path: str
    rows_written: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkbookVerificationResult:
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
