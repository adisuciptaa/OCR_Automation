"""Unit tests for conservative identifier normalization and validation."""
from __future__ import annotations

from features.tax_invoice.models import TaxInvoiceFieldValue
from features.tax_invoice.normalizer import (
    normalize_invoice_number,
    normalize_tax_invoice_number,
)
from features.tax_invoice.validator import TaxInvoiceValidator


def _field(field_id: str, raw: str) -> TaxInvoiceFieldValue:
    return TaxInvoiceFieldValue(
        field_id=field_id,
        raw_value=raw,
        normalized_value=None,
        page_index=0,
    )


def test_tax_invoice_number_accepts_canonical_and_compact_forms() -> None:
    assert normalize_tax_invoice_number("010.000-24.12345678") == "010.000-24.12345678"
    assert normalize_tax_invoice_number("0100002412345678") == "010.000-24.12345678"


def test_tax_invoice_number_rejects_wrong_length_and_ocr_guessing() -> None:
    assert normalize_tax_invoice_number("010.000-24.1234567") is None
    assert normalize_tax_invoice_number("O10.000-24.12345678") is None
    assert normalize_tax_invoice_number("010/000-24/12345678") is None


def test_invoice_number_removes_all_whitespace_and_preserves_case_and_punctuation() -> None:
    assert normalize_invoice_number("  INV\u00a0-  2026 / 01  ") == "INV-2026/01"
    assert normalize_invoice_number("inv 2026\t/\n001") == "inv2026/001"
    assert normalize_invoice_number("---") is None


def test_validator_marks_missing_or_invalid_fields_for_review() -> None:
    result = TaxInvoiceValidator().validate(_field("tax_invoice_number", "123"), None)
    assert result.status == "review"
    assert result.fields[0].status == "invalid"
    assert result.fields[0].reason_codes == ("TAX_INVOICE_NUMBER_INVALID_FORMAT",)
    assert result.fields[1].status == "missing"


def test_validator_detects_conflicting_values_across_pages() -> None:
    result = TaxInvoiceValidator().validate(
        _field("tax_invoice_number", "0100002412345678"),
        _field("invoice_number", "INV-01"),
        {
            "tax_invoice_number": ("0100002412345678", "0200002412345678"),
            "invoice_number": ("INV-01", "INV-01"),
        },
    )
    assert result.status == "review"
    assert result.fields[0].status == "conflict"
    assert "TAX_INVOICE_NUMBER_CONFLICTING_VALUES" in result.warnings
    assert result.fields[1].status == "valid"


def test_repeated_identical_values_are_not_treated_as_conflict() -> None:
    result = TaxInvoiceValidator().validate(
        _field("tax_invoice_number", "010.000-24.12345678"),
        _field("invoice_number", "INV-01"),
        {
            "tax_invoice_number": ("010.000-24.12345678", "0100002412345678"),
            "invoice_number": ("INV-01", "INV-01"),
        },
    )
    assert result.status == "valid"
    assert result.fields[0].normalized_value == "010.000-24.12345678"


def test_validator_flags_valid_and_invalid_duplicate_occurrences_as_ambiguous() -> None:
    result = TaxInvoiceValidator().validate(
        _field("tax_invoice_number", "0100002412345678"),
        _field("invoice_number", "INV-01"),
        {
            "tax_invoice_number": ("0100002412345678", "O100002412345678"),
            "invoice_number": ("INV-01",),
        },
    )
    assert result.status == "review"
    assert result.fields[0].status == "conflict"
    assert result.fields[0].reason_codes == ("TAX_INVOICE_NUMBER_AMBIGUOUS_OCCURRENCES",)
