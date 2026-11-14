"""Feature-owned immutable data models for Indonesian Tax Invoice Reader."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from app.services.models import NormalizedRegion

TaxInvoiceFieldId = Literal["tax_invoice_number", "invoice_number"]
ExtractionStatus = Literal["success", "review", "failed", "skipped"]
FieldValidationStatus = Literal["valid", "invalid", "missing", "conflict"]


@dataclass(frozen=True, slots=True)
class TaxInvoiceFieldValidation:
    """Validation decision for one extracted identifier."""

    field_id: TaxInvoiceFieldId
    status: FieldValidationStatus
    normalized_value: str | None = None
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"valid", "invalid", "missing", "conflict"}:
            raise ValueError("Unsupported field validation status.")
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        if self.status != "valid" and self.normalized_value is not None:
            raise ValueError("Only valid fields may expose a normalized value.")


@dataclass(frozen=True, slots=True)
class TaxInvoiceValidation:
    """Document-level validation summary, separate from raw OCR extraction."""

    status: Literal["valid", "review"]
    fields: tuple[TaxInvoiceFieldValidation, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"valid", "review"}:
            raise ValueError("Unsupported document validation status.")
        object.__setattr__(self, "fields", tuple(self.fields))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        field_ids = [item.field_id for item in self.fields]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("A validation result cannot contain duplicate field IDs.")
        if self.status == "valid" and any(item.status != "valid" for item in self.fields):
            raise ValueError("A valid document cannot contain non-valid fields.")


@dataclass(frozen=True, slots=True)
class TaxInvoiceFieldValue:
    """One extracted identifier with raw and normalized forms kept separately."""

    field_id: TaxInvoiceFieldId
    raw_value: str | None
    normalized_value: str | None
    page_index: int | None
    confidence: float | None = None
    confidence_kind: Literal["engine_score", "unavailable"] = "unavailable"

    def __post_init__(self) -> None:
        if self.field_id not in {"tax_invoice_number", "invoice_number"}:
            raise ValueError("Unsupported Tax Invoice field_id.")
        if self.confidence_kind not in {"engine_score", "unavailable"}:
            raise ValueError("Unsupported confidence_kind.")
        if self.page_index is not None and self.page_index < 0:
            raise ValueError("page_index must be zero-based and non-negative.")
        if self.confidence is not None and not math.isfinite(self.confidence):
            raise ValueError("confidence must be a finite engine score.")
        if self.confidence is None and self.confidence_kind != "unavailable":
            raise ValueError("confidence_kind must be unavailable when confidence is absent.")
        if self.confidence is not None and self.confidence_kind == "unavailable":
            raise ValueError("A supplied confidence value must be identified as an engine score.")


@dataclass(frozen=True, slots=True)
class TaxInvoicePageDetection:
    """Feature-specific decision for one zero-based PDF page."""

    page_index: int
    is_candidate: bool
    search_region: NormalizedRegion
    matched_markers: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    fallback_used: bool = False

    def __post_init__(self) -> None:
        if self.page_index < 0:
            raise ValueError("page_index must be zero-based and non-negative.")
        object.__setattr__(self, "matched_markers", tuple(self.matched_markers))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        if self.is_candidate and not self.matched_markers:
            raise ValueError("A candidate page must include at least one matched marker.")


@dataclass(frozen=True, slots=True)
class TaxInvoiceExtraction:
    """Structured extraction result for one source PDF."""

    source_path: str
    status: ExtractionStatus
    page_count: int
    detections: tuple[TaxInvoicePageDetection, ...]
    tax_invoice_number: TaxInvoiceFieldValue | None
    invoice_number: TaxInvoiceFieldValue | None
    warnings: tuple[str, ...] = ()
    error_code: str | None = None
    validation: TaxInvoiceValidation | None = None

    def __post_init__(self) -> None:
        if self.status not in {"success", "review", "failed", "skipped"}:
            raise ValueError("Unsupported extraction status.")
        if not self.source_path.strip():
            raise ValueError("source_path must be a non-empty string.")
        if self.page_count < 0:
            raise ValueError("page_count cannot be negative.")
        if any(item.page_index >= self.page_count for item in self.detections):
            raise ValueError("Detection page indexes must be within page_count.")
        if self.status == "failed" and not self.error_code:
            raise ValueError("A failed extraction must include an error_code.")
        if self.status != "failed" and self.error_code is not None:
            raise ValueError("error_code is only valid for a failed extraction.")
        if self.tax_invoice_number and self.tax_invoice_number.field_id != "tax_invoice_number":
            raise ValueError("tax_invoice_number contains the wrong field_id.")
        if self.invoice_number and self.invoice_number.field_id != "invoice_number":
            raise ValueError("invoice_number contains the wrong field_id.")
        if self.status == "success" and self.validation is not None and self.validation.status != "valid":
            raise ValueError("A successful extraction must have valid validation when supplied.")
        if self.status == "success" and self.validation is None:
            raise ValueError("A successful extraction must include a validation result.")
        object.__setattr__(self, "detections", tuple(self.detections))
        object.__setattr__(self, "warnings", tuple(self.warnings))
