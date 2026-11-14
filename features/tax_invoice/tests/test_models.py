import pytest

from app.services.models import NormalizedRegion
from features.tax_invoice.models import (
    TaxInvoiceExtraction,
    TaxInvoiceFieldValue,
    TaxInvoicePageDetection,
)


def test_field_value_keeps_raw_and_normalized_values_separate():
    field = TaxInvoiceFieldValue(
        "tax_invoice_number", "010.000-24.12345678", "0100002412345678",
        page_index=0, confidence=92.5, confidence_kind="engine_score",
    )
    assert field.raw_value != field.normalized_value
    assert field.confidence == 92.5


def test_field_value_rejects_confidence_without_semantics():
    with pytest.raises(ValueError):
        TaxInvoiceFieldValue("invoice_number", "INV-1", "INV-1", 0, confidence=0.9)


def test_candidate_detection_requires_marker():
    with pytest.raises(ValueError):
        TaxInvoicePageDetection(0, True, NormalizedRegion(0, 0, 1, 0.25))


def test_extraction_requires_error_code_for_failure():
    with pytest.raises(ValueError):
        TaxInvoiceExtraction("a.pdf", "failed", 1, (), None, None)


def test_extraction_rejects_page_index_outside_document():
    detection = TaxInvoicePageDetection(
        1, True, NormalizedRegion(0, 0, 1, 0.25), matched_markers=("FAKTUR PAJAK",)
    )
    with pytest.raises(ValueError):
        TaxInvoiceExtraction("a.pdf", "review", 1, (detection,), None, None)


def test_extraction_accepts_review_result():
    detection = TaxInvoicePageDetection(
        0, True, NormalizedRegion(0, 0, 1, 0.25), matched_markers=("FAKTUR PAJAK",)
    )
    result = TaxInvoiceExtraction("a.pdf", "review", 1, (detection,), None, None)
    assert result.detections[0].page_index == 0


def test_field_value_rejects_unknown_field_id():
    with pytest.raises(ValueError):
        TaxInvoiceFieldValue("unknown", "x", "x", 0)
