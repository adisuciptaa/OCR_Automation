"""Feature-owned validation rules for extracted Tax Invoice identifiers."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from features.tax_invoice.models import (
    TaxInvoiceFieldValidation,
    TaxInvoiceFieldValue,
    TaxInvoiceValidation,
)
from features.tax_invoice.normalizer import (
    normalize_invoice_number,
    normalize_tax_invoice_number,
)


class TaxInvoiceValidator:
    """Validate identifiers without silently repairing uncertain OCR output."""

    def validate(
        self,
        tax_invoice_number: TaxInvoiceFieldValue | None,
        invoice_number: TaxInvoiceFieldValue | None,
        occurrences: Mapping[str, Sequence[str]] | None = None,
    ) -> TaxInvoiceValidation:
        occurrences = occurrences or {}
        fields = (
            self._validate_field("tax_invoice_number", tax_invoice_number,
                                 occurrences.get("tax_invoice_number", ()),
                                 normalize_tax_invoice_number, "TAX_INVOICE_NUMBER"),
            self._validate_field("invoice_number", invoice_number,
                                 occurrences.get("invoice_number", ()),
                                 normalize_invoice_number, "INVOICE_NUMBER"),
        )
        warnings = tuple(dict.fromkeys(
            reason for field in fields for reason in field.reason_codes
        ))
        status = "valid" if all(field.status == "valid" for field in fields) else "review"
        return TaxInvoiceValidation(status=status, fields=fields, warnings=warnings)

    @staticmethod
    def _validate_field(field_id, value, raw_occurrences, normalizer, code_prefix):
        if value is None or not value.raw_value:
            return TaxInvoiceFieldValidation(
                field_id=field_id, status="missing", reason_codes=(f"{code_prefix}_MISSING",)
            )
        normalized = normalizer(value.raw_value)
        if normalized is None:
            return TaxInvoiceFieldValidation(
                field_id=field_id, status="invalid", reason_codes=(f"{code_prefix}_INVALID_FORMAT",)
            )
        normalized_occurrences: set[str] = set()
        invalid_occurrence = False
        for raw in raw_occurrences:
            candidate = normalizer(raw)
            if candidate is None:
                invalid_occurrence = True
            else:
                normalized_occurrences.add(candidate)
        if len(normalized_occurrences) > 1 or invalid_occurrence:
            reason = (
                f"{code_prefix}_CONFLICTING_VALUES"
                if len(normalized_occurrences) > 1
                else f"{code_prefix}_AMBIGUOUS_OCCURRENCES"
            )
            return TaxInvoiceFieldValidation(
                field_id=field_id, status="conflict", reason_codes=(reason,),
            )
        return TaxInvoiceFieldValidation(
            field_id=field_id, status="valid", normalized_value=normalized,
        )
