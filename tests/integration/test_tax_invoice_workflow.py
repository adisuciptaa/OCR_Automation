"""End-to-end feature workflow tests using synthetic documents and a real Excel adapter."""
from __future__ import annotations

import logging
from copy import deepcopy
from types import SimpleNamespace

from openpyxl import Workbook, load_workbook

from app.core.event_bus import EventBus
from app.core.exceptions import ApplicationError
from app.core.job_contracts import JobRequest
from app.core.service_registry import ServiceRegistry
from app.feature_manager.runtime_contracts import FeatureContext
from app.services.excel.adapters import OpenpyxlExcelAdapter
from app.services.registration import SharedServiceImplementations, register_shared_services
from features.tax_invoice.config import default_configuration
from features.tax_invoice.entry import TaxInvoiceFeature


class _UnusedService:
    pass


class _FakeExtractor:
    def __init__(self, pdf, ocr, configuration) -> None:
        self.configuration = configuration

    def process(self, path: str):
        if path == "corrupt.pdf":
            raise ApplicationError("PDF_CORRUPT", "The PDF document is corrupt.")
        if path == "needs-review.pdf":
            return SimpleNamespace(
                status="review", tax_invoice_number=None, invoice_number=None,
                validation=None, warnings=("TAX_INVOICE_MARKER_NOT_FOUND",), error_code=None,
            )
        tax_number = SimpleNamespace(
            raw_value="010.000-24.12345678",
            normalized_value="010.000-24.12345678",
            page_index=0,
            confidence=91.0,
            confidence_kind="engine_score",
        )
        invoice_number = SimpleNamespace(
            raw_value="INV 2026 / 001",
            normalized_value="INV2026/001",
            page_index=0,
            confidence=89.0,
            confidence_kind="engine_score",
        )
        return SimpleNamespace(
            status="success", tax_invoice_number=tax_number, invoice_number=invoice_number,
            validation=None, warnings=(), error_code=None,
        )


def _make_feature(monkeypatch) -> TaxInvoiceFeature:
    registry = ServiceRegistry()
    register_shared_services(
        registry,
        SharedServiceImplementations(
            pdf=_UnusedService(),
            ocr=_UnusedService(),
            image=_UnusedService(),
            excel=OpenpyxlExcelAdapter(),
            validation=_UnusedService(),
            reporting=_UnusedService(),
        ),
    )
    monkeypatch.setattr("features.tax_invoice.entry.TaxInvoiceExtractor", _FakeExtractor)
    feature = TaxInvoiceFeature()
    feature.initialize(
        FeatureContext(registry.provider, EventBus(), logging.getLogger("tax-invoice-integration"), "tax_invoice")
    )
    return feature


def test_mixed_batch_writes_only_success_and_preserves_source_workbook(tmp_path, monkeypatch) -> None:
    source = tmp_path / "tracking.xlsx"
    destination = tmp_path / "tracking-output.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Invoices"
    sheet.append(["Invoice Number", "Tax Invoice Number"])
    sheet.append(["INV2026/001", None])
    workbook.save(source)
    source_before = source.read_bytes()

    configuration = deepcopy(dict(default_configuration()))
    configuration["excel"] = {
        "source_workbook_path": str(source),
        "worksheet": "Invoices",
        "header_row": 1,
        "data_start_row": 2,
        "source_key_column": "Invoice Number",
        "target_column": "Tax Invoice Number",
        "match_field": "invoice_number",
        "write_field": "tax_invoice_number",
        "key_type": "text",
        "normalization_profile": "remove_whitespace",
        "duplicate_policy": "review",
        "unmatched_policy": "report",
        "overwrite_policy": "empty_only",
    }
    feature = _make_feature(monkeypatch)
    request = JobRequest(
        job_id="integration-mixed-batch",
        feature_id="tax_invoice",
        input_paths=("success.pdf", "needs-review.pdf", "corrupt.pdf"),
        output_path=str(destination),
        configuration=configuration,
        requested_by="integration-test",
        correlation_id="integration-correlation",
    )

    result = feature.execute(request)

    assert [item.status for item in result.results] == ["success", "review", "failed"]
    assert (result.successful_files, result.review_files, result.failed_files) == (1, 1, 1)
    assert result.status == "completed_with_warnings"
    assert result.output_path == str(destination)
    assert source.read_bytes() == source_before

    output_sheet = load_workbook(destination, data_only=False)["Invoices"]
    assert output_sheet.cell(row=2, column=1).value == "INV2026/001"
    assert output_sheet.cell(row=2, column=2).value == "010.000-24.12345678"
    assert result.results[1].warnings == ("TAX_INVOICE_MARKER_NOT_FOUND",)
    assert result.results[2].error_code == "PDF_CORRUPT"


def test_unexpected_excel_adapter_error_marks_successful_documents_failed(monkeypatch) -> None:
    class BrokenExcelService:
        def inspect_workbook(self, path: str):
            raise RuntimeError("adapter internals must not leak into job result")

    registry = ServiceRegistry()
    register_shared_services(
        registry,
        SharedServiceImplementations(
            pdf=_UnusedService(), ocr=_UnusedService(), image=_UnusedService(),
            excel=BrokenExcelService(), validation=_UnusedService(), reporting=_UnusedService(),
        ),
    )
    monkeypatch.setattr("features.tax_invoice.entry.TaxInvoiceExtractor", _FakeExtractor)
    feature = TaxInvoiceFeature()
    feature.initialize(
        FeatureContext(registry.provider, EventBus(), logging.getLogger("tax-invoice-integration"), "tax_invoice")
    )
    configuration = deepcopy(dict(default_configuration()))
    configuration["excel"] = {
        "source_workbook_path": "source.xlsx", "worksheet": "Invoices",
        "header_row": 1, "data_start_row": 2, "source_key_column": "Invoice Number",
        "target_column": "Tax Invoice Number", "match_field": "invoice_number",
        "write_field": "tax_invoice_number", "key_type": "text",
        "normalization_profile": "remove_whitespace", "duplicate_policy": "review",
        "unmatched_policy": "report", "overwrite_policy": "empty_only",
    }
    request = JobRequest(
        job_id="integration-excel-error", feature_id="tax_invoice", input_paths=("success.pdf",),
        output_path="output.xlsx", configuration=configuration, requested_by="integration-test",
        correlation_id="integration-error-correlation",
    )

    result = feature.execute(request)

    assert result.status == "failed"
    assert result.successful_files == 0
    assert result.failed_files == 1
    assert result.results[0].error_code == "TAX_INVOICE_EXCEL_OUTPUT_FAILED"


def test_successful_extraction_without_excel_match_becomes_need_review(monkeypatch) -> None:
    from app.services.excel.models import ExcelReadResult, ExcelWriteResult, WorkbookDescriptor

    class NoMatchExcelService:
        def inspect_workbook(self, path: str):
            return WorkbookDescriptor(path, ("Invoices",), "xlsx")

        def read_records(self, request):
            return ExcelReadResult(())

        def write_records(self, request):
            return ExcelWriteResult(request.destination_path, 0, ("EXCEL_NO_MATCHING_ROWS",))

    registry = ServiceRegistry()
    register_shared_services(
        registry,
        SharedServiceImplementations(
            pdf=_UnusedService(), ocr=_UnusedService(), image=_UnusedService(),
            excel=NoMatchExcelService(), validation=_UnusedService(), reporting=_UnusedService(),
        ),
    )
    monkeypatch.setattr("features.tax_invoice.entry.TaxInvoiceExtractor", _FakeExtractor)
    feature = TaxInvoiceFeature()
    feature.initialize(
        FeatureContext(registry.provider, EventBus(), logging.getLogger("tax-invoice-integration"), "tax_invoice")
    )
    configuration = deepcopy(dict(default_configuration()))
    configuration["excel"] = {
        "source_workbook_path": "source.xlsx", "worksheet": "Invoices",
        "header_row": 1, "data_start_row": 2, "source_key_column": "Invoice Number",
        "target_column": "Tax Invoice Number", "match_field": "invoice_number",
        "write_field": "tax_invoice_number", "key_type": "text",
        "normalization_profile": "remove_whitespace", "duplicate_policy": "review",
        "unmatched_policy": "report", "overwrite_policy": "empty_only",
    }
    request = JobRequest(
        job_id="integration-no-excel-match", feature_id="tax_invoice", input_paths=("success.pdf",),
        output_path="output.xlsx", configuration=configuration, requested_by="integration-test",
        correlation_id="integration-no-match-correlation",
    )

    result = feature.execute(request)

    assert result.status == "completed_with_warnings"
    assert result.successful_files == 0
    assert result.review_files == 1
    assert result.failed_files == 0
    assert result.output_path is None
    assert result.results[0].status == "review"
