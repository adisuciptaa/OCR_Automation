"""Tax Invoice Excel output policy tests: only successful files may be written."""
from __future__ import annotations

from app.core.job_contracts import FileResult
from app.services.excel.models import (
    ExcelReadResult,
    ExcelRecord,
    ExcelWriteResult,
    WorkbookDescriptor,
)
from features.tax_invoice.excel_output import write_validated_results


class FakeExcelService:
    def __init__(self) -> None:
        self.write_requests = []
        self.read_requests = []

    def inspect_workbook(self, path: str) -> WorkbookDescriptor:
        return WorkbookDescriptor(path, ("Invoices",), "xlsx")

    def read_records(self, request):
        self.read_requests.append(request)
        return ExcelReadResult(())

    def write_records(self, request):
        self.write_requests.append(request)
        return ExcelWriteResult("/tmp/output.xlsx", len(request.records))


CONFIG = {
    "source_workbook_path": "/tmp/source.xlsx",
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


def _result(path: str, status: str) -> FileResult:
    fields = {
        "invoice_number": {"raw_value": "INV 2026 001", "normalized_value": "INV2026001"},
        "tax_invoice_number": {
            "raw_value": "0100002412345678",
            "normalized_value": "010.000-24.12345678",
        },
    }
    return FileResult(
        source_path=path,
        status=status,
        extracted_fields=fields,
        confidence={},
        warnings=("manual review",) if status == "review" else (),
        error_code="PDF_CORRUPT" if status == "failed" else None,
    )


def test_only_success_results_are_passed_to_excel_write_service() -> None:
    service = FakeExcelService()
    results = (_result("success.pdf", "success"), _result("review.pdf", "review"), _result("failed.pdf", "failed"))

    finalized, output_path, warnings = write_validated_results(
        service, results=results, configuration=CONFIG, destination_path="/tmp/output.xlsx"
    )

    assert output_path == "/tmp/output.xlsx"
    assert not warnings
    assert len(service.write_requests) == 1
    records = service.write_requests[0].records
    assert len(records) == 1
    assert dict(records[0].values) == {
        "Invoice Number": "INV2026001",
        "Tax Invoice Number": "010.000-24.12345678",
    }
    assert [item.status for item in finalized] == ["success", "review", "failed"]


def test_review_and_failed_only_batch_never_calls_excel_services() -> None:
    service = FakeExcelService()
    results = (_result("review.pdf", "review"), _result("failed.pdf", "failed"))

    finalized, output_path, warnings = write_validated_results(
        service, results=results, configuration=CONFIG, destination_path="/tmp/output.xlsx"
    )

    assert output_path is None
    assert "EXCEL_NO_ELIGIBLE_SUCCESS_RESULTS" in warnings
    assert service.read_requests == []
    assert service.write_requests == []
    assert [item.status for item in finalized] == ["review", "failed"]


def test_success_without_required_normalized_field_is_downgraded_to_review() -> None:
    service = FakeExcelService()
    result = _result("missing.pdf", "success")
    fields = dict(result.extracted_fields)
    fields["invoice_number"] = {"raw_value": "", "normalized_value": None}
    result = FileResult(result.source_path, "success", fields, {}, ())

    finalized, output_path, warnings = write_validated_results(
        service, results=(result,), configuration=CONFIG, destination_path="/tmp/output.xlsx"
    )

    assert output_path is None
    assert finalized[0].status == "review"
    assert any("EXCEL_REQUIRED_IDENTIFIER_MISSING" in item for item in finalized[0].warnings)
    assert service.write_requests == []


def test_excel_mapping_rejects_same_match_and_write_field() -> None:
    import pytest

    from app.core.exceptions import ApplicationError

    service = FakeExcelService()
    configuration = dict(CONFIG, write_field="invoice_number")
    with pytest.raises(ApplicationError) as error:
        write_validated_results(
            service,
            results=(_result("success.pdf", "success"),),
            configuration=configuration,
            destination_path="/tmp/output.xlsx",
        )
    assert error.value.code == "EXCEL_MAPPING_INVALID"
    assert service.write_requests == []


def test_feature_execute_keeps_review_out_of_excel_write(monkeypatch) -> None:
    import logging
    from types import SimpleNamespace

    from app.core.event_bus import EventBus
    from app.core.job_contracts import JobRequest
    from app.core.service_registry import ServiceRegistry
    from app.feature_manager.runtime_contracts import FeatureContext
    from app.services.registration import SharedServiceImplementations, register_shared_services
    from features.tax_invoice.entry import TaxInvoiceFeature

    class FakeProcessor:
        def __init__(self, pdf, ocr, configuration):
            pass

        def process(self, path):
            if path == "review.pdf":
                return SimpleNamespace(
                    status="review", tax_invoice_number=None, invoice_number=None,
                    validation=None, warnings=("NEED_REVIEW",), error_code=None,
                )
            tax = SimpleNamespace(
                raw_value="0100002412345678", normalized_value="010.000-24.12345678",
                page_index=0, confidence=None, confidence_kind="unavailable",
            )
            invoice = SimpleNamespace(
                raw_value="INV 2026 001", normalized_value="INV2026001",
                page_index=0, confidence=None, confidence_kind="unavailable",
            )
            return SimpleNamespace(
                status="success", tax_invoice_number=tax, invoice_number=invoice,
                validation=SimpleNamespace(status="valid", fields=(), warnings=()),
                warnings=(), error_code=None,
            )

    class FakeServiceProvider:
        def __init__(self, excel):
            self.excel = excel

        def get(self, service_id, version=None):
            if service_id == "excel.workbook":
                return self.excel
            return object()

    class FakePDF:
        pass

    class FakeOCR:
        pass

    class FakeImage:
        pass

    class FakeValidation:
        pass

    class FakeReporting:
        pass

    excel = FakeExcelService()
    registry = ServiceRegistry()
    register_shared_services(
        registry,
        SharedServiceImplementations(
            pdf=FakePDF(), ocr=FakeOCR(), image=FakeImage(), excel=excel,
            validation=FakeValidation(), reporting=FakeReporting(),
        ),
    )
    monkeypatch.setattr("features.tax_invoice.entry.TaxInvoiceExtractor", FakeProcessor)
    feature = TaxInvoiceFeature()
    feature.initialize(FeatureContext(registry.provider, EventBus(), logging.getLogger("test"), "tax_invoice"))
    configuration = {
        "detection": {"top_region_ratio": 0.25, "marker_phrases": ["FAKTUR PAJAK"], "fallback_full_page": False},
        "ocr": {"prefer_embedded_text": True, "language": "ind+eng"},
        "processing": {"max_pages_per_document": 200, "render_dpi": 200},
        "excel": CONFIG,
    }
    request = JobRequest(
        job_id="job-excel", feature_id="tax_invoice",
        input_paths=("success.pdf", "review.pdf"), output_path="/tmp/output.xlsx",
        configuration=configuration, requested_by="tester", correlation_id="corr-excel",
    )

    result = feature.execute(request)

    assert result.successful_files == 1
    assert result.review_files == 1
    assert result.failed_files == 0
    assert result.output_path == "/tmp/output.xlsx"
    assert len(excel.write_requests) == 1
    assert len(excel.write_requests[0].records) == 1
    assert dict(excel.write_requests[0].records[0].values)["Invoice Number"] == "INV2026001"


def test_excel_output_integration_preserves_source_and_writes_validated_pair(tmp_path) -> None:
    from openpyxl import Workbook, load_workbook

    from app.services.excel.adapters import OpenpyxlExcelAdapter

    source = tmp_path / "tracking.xlsx"
    destination = tmp_path / "tracking-output.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Invoices"
    sheet.append(["Invoice Number", "Tax Invoice Number"])
    sheet.append(["INV 2026 / 001", None])
    workbook.save(source)

    configuration = dict(CONFIG, source_workbook_path=str(source))
    success = _result("success.pdf", "success")
    success_fields = dict(success.extracted_fields)
    success_fields["invoice_number"] = {
        "raw_value": "INV 2026 / 001", "normalized_value": "INV2026/001"
    }
    success = FileResult(success.source_path, "success", success_fields, {}, ())
    results = (success, _result("review.pdf", "review"))
    finalized, output_path, warnings = write_validated_results(
        OpenpyxlExcelAdapter(),
        results=results,
        configuration=configuration,
        destination_path=str(destination),
    )

    assert output_path == str(destination)
    assert not warnings
    assert [item.status for item in finalized] == ["success", "review"]
    original = load_workbook(source)
    output = load_workbook(destination)
    assert original["Invoices"]["B2"].value is None
    assert output["Invoices"]["B2"].value == "010.000-24.12345678"


def test_invoice_match_defaults_to_whitespace_removal_profile() -> None:
    service = FakeExcelService()
    configuration = dict(CONFIG)
    configuration.pop("normalization_profile")

    write_validated_results(
        service,
        results=(_result("success.pdf", "success"),),
        configuration=configuration,
        destination_path="/tmp/output.xlsx",
    )

    assert service.write_requests[0].mapping.normalization_profile == "remove_whitespace"
