"""Unit tests for Tax Invoice page detection and raw extraction."""
from __future__ import annotations

from collections.abc import Mapping

import pytest

from app.core.exceptions import ApplicationError
from app.services.ocr.models import OCRResult
from app.services.pdf.models import PDFMetadata, RenderedPage
from features.tax_invoice.config import default_configuration
from features.tax_invoice.extractor import TaxInvoiceExtractor


class FakePDF:
    def __init__(self, embedded: tuple[str, ...] = (), page_count: int | None = None) -> None:
        self.embedded = embedded
        self.page_count = page_count if page_count is not None else max(1, len(embedded))
        self.render_calls: list[tuple[int, object]] = []

    def inspect(self, path: str) -> PDFMetadata:
        return PDFMetadata(self.page_count, 1234, False)

    def extract_embedded_text(self, path: str, page_index: int) -> str:
        return self.embedded[page_index] if page_index < len(self.embedded) else ""

    def render_page(self, path: str, page_index: int, dpi: int, region=None) -> RenderedPage:
        self.render_calls.append((page_index, region))
        return RenderedPage(b"image", "image/png", 100, 100, page_index, dpi)


class FakeOCR:
    def __init__(self, texts: list[str]) -> None:
        self.texts = iter(texts)
        self.calls = 0

    def recognize(self, image, options) -> OCRResult:
        self.calls += 1
        return OCRResult(
            text=next(self.texts), lines=(), engine_id="fake", engine_version="1",
            languages=options.languages, confidence=87.5, confidence_kind="engine_score",
        )


def _config(**overrides: object) -> Mapping[str, object]:
    config = default_configuration()
    detection = dict(config["detection"])
    ocr = dict(config["ocr"])
    processing = dict(config["processing"])
    detection.update(overrides.get("detection", {}))
    ocr.update(overrides.get("ocr", {}))
    processing.update(overrides.get("processing", {}))
    return {"detection": detection, "ocr": ocr, "processing": processing}


def test_embedded_text_detects_and_extracts_both_raw_identifiers() -> None:
    pdf = FakePDF((
        "FAKTUR PAJAK\nKode dan Nomor Seri Faktur Pajak: 010.000-24.12345678\n"
        "Nomor Invoice: INV-2024-001",
    ))
    extractor = TaxInvoiceExtractor(pdf, FakeOCR([]), _config())

    result = extractor.process("sample.pdf")

    assert result.status == "success"
    assert result.detections[0].is_candidate is True
    assert result.tax_invoice_number.raw_value == "010.000-24.12345678"
    assert result.invoice_number.raw_value == "INV-2024-001"
    assert result.tax_invoice_number.normalized_value == "010.000-24.12345678"
    assert result.invoice_number.normalized_value == "INV-2024-001"
    assert result.validation.status == "valid"
    assert result.tax_invoice_number.confidence_kind == "unavailable"
    assert pdf.render_calls == []


def test_scanned_page_uses_top_region_detection_then_full_page_extraction() -> None:
    pdf = FakePDF((), page_count=1)
    ocr = FakeOCR([
        "FAKTUR PAJAK",  # top-region candidate detection
        "FAKTUR PAJAK\nNomor Faktur Pajak: 0100002412345678\nInvoice No: INV-77",
    ])
    result = TaxInvoiceExtractor(pdf, ocr, _config()).process("scan.pdf")

    assert result.status == "success"
    assert ocr.calls == 2
    assert result.tax_invoice_number.raw_value == "0100002412345678"
    assert result.invoice_number.raw_value == "INV-77"
    assert result.tax_invoice_number.confidence == 87.5
    assert result.tax_invoice_number.confidence_kind == "engine_score"
    assert pdf.render_calls[0][1].height == 0.25
    assert pdf.render_calls[1][1].height == 1.0


def test_full_page_fallback_is_only_used_when_configured() -> None:
    pdf = FakePDF((), page_count=1)
    ocr = FakeOCR(["header without marker", "FAKTUR PAJAK\nNomor Invoice: INV-1"])
    config = _config(detection={"fallback_full_page": True})

    result = TaxInvoiceExtractor(pdf, ocr, config).process("scan.pdf")

    assert result.detections[0].is_candidate is True
    assert result.detections[0].fallback_used is True
    assert result.detections[0].search_region.height == 1.0
    assert ocr.calls == 2


def test_no_marker_returns_review_without_fabricating_fields() -> None:
    pdf = FakePDF(("ordinary document",))
    result = TaxInvoiceExtractor(pdf, FakeOCR(["still ordinary"]), _config()).process("plain.pdf")

    assert result.status == "review"
    assert result.tax_invoice_number is None
    assert result.invoice_number is None
    assert "TAX_INVOICE_MARKER_NOT_FOUND" in result.warnings


def test_page_limit_is_enforced_before_rendering() -> None:
    pdf = FakePDF((), page_count=3)
    extractor = TaxInvoiceExtractor(pdf, FakeOCR([]), _config(processing={"max_pages_per_document": 2}))

    with pytest.raises(ApplicationError) as error:
        extractor.process("large.pdf")

    assert error.value.code == "TAX_INVOICE_PAGE_LIMIT"
    assert pdf.render_calls == []


def test_feature_execute_returns_per_file_review_and_success_results() -> None:
    import logging

    from app.core.event_bus import EventBus
    from app.core.job_contracts import JobRequest
    from app.core.service_registry import ServiceRegistry
    from app.feature_manager.runtime_contracts import FeatureContext
    from app.services.registration import register_shared_services, SharedServiceImplementations
    from features.tax_invoice.entry import TaxInvoiceFeature

    class FakeValidation:
        pass

    class FakeImage:
        pass

    class FakeExcel:
        pass

    class FakeReporting:
        pass

    pdf = FakePDF(("FAKTUR PAJAK\nNomor Faktur Pajak: 0100002412345678\nNomor Invoice: INV-1",))
    ocr = FakeOCR(["no marker", "no marker"])
    registry = ServiceRegistry()
    register_shared_services(registry, SharedServiceImplementations(
        pdf=pdf, ocr=ocr, image=FakeImage(), excel=FakeExcel(),
        validation=FakeValidation(), reporting=FakeReporting(),
    ))
    feature = TaxInvoiceFeature()
    feature.initialize(FeatureContext(registry.provider, EventBus(), logging.getLogger("test"), "tax_invoice"))
    request = JobRequest(
        job_id="job-1", feature_id="tax_invoice", input_paths=("valid.pdf",),
        output_path="result.xlsx", configuration=_config(), requested_by="tester", correlation_id="corr-1",
    )

    result = feature.execute(request)

    assert result.status == "completed"
    assert result.successful_files == 1
    assert result.review_files == 0
    assert result.failed_files == 0
    assert result.output_path is None  # Excel mapping is optional until configured.


def test_older_configuration_without_render_dpi_uses_backward_compatible_default() -> None:
    configuration = _config()
    processing = dict(configuration["processing"])
    processing.pop("render_dpi")
    old_profile = {
        "detection": dict(configuration["detection"]),
        "ocr": dict(configuration["ocr"]),
        "processing": processing,
    }
    extractor = TaxInvoiceExtractor(FakePDF(("FAKTUR PAJAK",)), FakeOCR([]), old_profile)

    assert extractor._dpi == 200


def test_extractor_marks_conflicting_identifiers_across_candidate_pages_for_review() -> None:
    pdf = FakePDF((
        "FAKTUR PAJAK\nNomor Faktur Pajak: 010.000-24.12345678\nNomor Invoice: INV-01",
        "FAKTUR PAJAK\nNomor Faktur Pajak: 020.000-24.12345678\nNomor Invoice: INV-01",
    ), page_count=2)
    result = TaxInvoiceExtractor(pdf, FakeOCR([]), _config()).process("multi-page.pdf")

    assert result.status == "review"
    assert result.tax_invoice_number.normalized_value is None
    assert result.invoice_number.normalized_value == "INV-01"
    assert result.validation.status == "review"
    assert "TAX_INVOICE_NUMBER_CONFLICTING_VALUES" in result.warnings
