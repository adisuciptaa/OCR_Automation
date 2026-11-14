"""Manifest-backed Tax Invoice feature runtime entry point."""
from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.core.exceptions import ApplicationError
from app.core.job_contracts import FileResult, JobRequest, JobResult
from app.feature_manager.configuration_manager import FeatureConfigurationManagerService
from app.feature_manager.models import FeatureDescriptor
from app.feature_manager.runtime_contracts import FeatureContext, UIContext
from features.tax_invoice.config import default_configuration
from features.tax_invoice.extractor import TaxInvoiceExtractor
from features.tax_invoice.excel_output import write_validated_results


class TaxInvoiceFeature:
    """Feature lifecycle and application-contract adapter for Tax Invoice processing."""

    FEATURE_ID = "tax_invoice"
    DISPLAY_NAME = "Pembacaan Faktur Pajak"
    DESCRIPTION = (
        "Mendeteksi halaman faktur pajak dan mengekstraksi nomor faktur pajak "
        "serta nomor invoice terkait."
    )
    VERSION = "1.0.0"
    ICON = "file-search"
    REQUIRED_PERMISSIONS = (
        "filesystem.read_input",
        "filesystem.write_output",
        "pdf.read",
        "ocr.execute",
        "excel.read",
        "excel.write",
    )
    LICENSE_ENTITLEMENT = None

    def __init__(self) -> None:
        self._context: FeatureContext | None = None
        self._execution_lock = threading.RLock()
        self._worker_registry_lock = threading.RLock()
        self._active_workers: set[object] = set()

    def initialize(self, context: FeatureContext) -> None:
        if context.feature_id != self.FEATURE_ID:
            raise ApplicationError("FEATURE_CONTEXT_INVALID", "Feature runtime context does not match this feature.")
        # Resolve declared services now so missing dependencies fail during activation, not mid-job.
        context.services.get("pdf.render", "1.0.0")
        context.services.get("ocr.recognize", "1.0.0")
        context.services.get("excel.workbook", "1.0.0")
        self._context = context

    def get_descriptor(self) -> FeatureDescriptor:
        return FeatureDescriptor(
            self.FEATURE_ID, self.DISPLAY_NAME, self.DESCRIPTION, self.VERSION,
            self.ICON, self.REQUIRED_PERMISSIONS, self.LICENSE_ENTITLEMENT,
        )

    def create_workspace(self, context: UIContext) -> object:
        from PySide6.QtWidgets import QWidget
        from .ui import TaxInvoiceWorkspace

        if self._context is None:
            raise ApplicationError("FEATURE_NOT_INITIALIZED", "Tax Invoice feature is not initialized.")
        if context.feature_id != self.FEATURE_ID or not isinstance(context.parent, QWidget):
            raise ApplicationError("FEATURE_WORKSPACE_INVALID", "Tax Invoice workspace context is invalid.")
        return TaxInvoiceWorkspace(feature=self, actor_id=context.actor_id, parent=context.parent)

    def validate_configuration(self, config: Mapping[str, object]) -> Mapping[str, object]:
        if not isinstance(config, Mapping):
            raise ApplicationError("FEATURE_CONFIGURATION_INVALID", "Tax Invoice configuration must be an object.")
        schema_path = Path(__file__).with_name("config_schema.json")
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApplicationError(
                "FEATURE_CONFIGURATION_SCHEMA_INVALID", "Tax Invoice configuration schema is unavailable."
            ) from exc
        values = _to_plain_dict(config)
        FeatureConfigurationManagerService._validate_schema_definition(schema)
        FeatureConfigurationManagerService._validate_configuration(schema, values)
        excel_config = values.get("excel")
        if isinstance(excel_config, dict):
            if excel_config.get("match_field") == excel_config.get("write_field"):
                raise ApplicationError(
                    "FEATURE_CONFIGURATION_INVALID",
                    "Excel match_field and write_field must refer to different extracted fields.",
                )
            if not str(excel_config.get("source_workbook_path", "")).strip():
                raise ApplicationError(
                    "FEATURE_CONFIGURATION_INVALID",
                    "Excel source_workbook_path must point to an existing source workbook.",
                )
        return config

    def execute(self, request: JobRequest) -> JobResult:
        with self._execution_lock:
            return self._execute_locked(request)

    def _execute_locked(self, request: JobRequest) -> JobResult:
        if self._context is None:
            raise ApplicationError("FEATURE_NOT_INITIALIZED", "Tax Invoice feature is not initialized.")
        if request.feature_id != self.FEATURE_ID:
            raise ApplicationError("FEATURE_REQUEST_INVALID", "Job request targets a different feature.")
        configuration = request.configuration or default_configuration()
        self.validate_configuration(configuration)
        pdf = self._context.services.get("pdf.render", "1.0.0")
        ocr = self._context.services.get("ocr.recognize", "1.0.0")
        processor = TaxInvoiceExtractor(pdf, ocr, configuration)

        results: list[FileResult] = []
        for source_path in request.input_paths:
            try:
                extraction = processor.process(source_path)
                fields: dict[str, object] = {}
                confidence: dict[str, float] = {}
                for field_id, value in (
                    ("tax_invoice_number", extraction.tax_invoice_number),
                    ("invoice_number", extraction.invoice_number),
                ):
                    if value is not None:
                        fields[field_id] = {
                            "raw_value": value.raw_value,
                            "normalized_value": value.normalized_value,
                            "page_index": value.page_index,
                            "confidence_kind": value.confidence_kind,
                        }
                        if value.confidence is not None:
                            confidence[field_id] = value.confidence
                if extraction.validation is not None:
                    fields["_validation"] = {
                        "status": extraction.validation.status,
                        "fields": {
                            item.field_id: {
                                "status": item.status,
                                "normalized_value": item.normalized_value,
                                "reason_codes": item.reason_codes,
                            }
                            for item in extraction.validation.fields
                        },
                    }
                results.append(FileResult(
                    source_path=source_path,
                    status=extraction.status,
                    extracted_fields=fields,
                    confidence=confidence,
                    warnings=extraction.warnings,
                    error_code=extraction.error_code,
                ))
            except ApplicationError as exc:
                results.append(FileResult(
                    source_path=source_path, status="failed", extracted_fields={}, confidence={},
                    warnings=(exc.safe_message,), error_code=exc.code,
                ))
            except Exception:
                self._context.logger.exception("Unexpected Tax Invoice processing failure for one input file")
                results.append(FileResult(
                    source_path=source_path, status="failed", extracted_fields={}, confidence={},
                    warnings=("An unexpected error occurred while processing this document.",),
                    error_code="TAX_INVOICE_PROCESSING_FAILED",
                ))

        output_path: str | None = None
        excel_config = configuration.get("excel")
        if isinstance(excel_config, Mapping):
            try:
                excel_service = self._context.services.get("excel.workbook", "1.0.0")
                finalized, output_path, excel_warnings = write_validated_results(
                    excel_service,
                    results=tuple(results),
                    configuration=excel_config,
                    destination_path=request.output_path,
                )
                results = list(finalized)
                if "EXCEL_NO_ROWS_WRITTEN" in excel_warnings:
                    results = [
                        _change_result_status(
                            item, "review", None,
                            "No matching or writable Excel row was found; manual review is required.",
                        ) if item.status == "success" else item
                        for item in results
                    ]
                    output_path = None
                if excel_warnings:
                    results = _append_warnings_to_successes(results, excel_warnings)
            except ApplicationError as exc:
                self._context.logger.exception("Tax Invoice Excel mapping/output failed")
                if exc.code == "EXCEL_NO_ROWS_WRITTEN":
                    results = [
                        _change_result_status(
                            item, "review", None,
                            "No matching or writable Excel row was found; manual review is required.",
                        ) if item.status == "success" else item
                        for item in results
                    ]
                else:
                    results = [
                        _change_result_status(
                            item, "failed", exc.code,
                            "Excel mapping/output failed; this document was not written to the workbook.",
                        ) if item.status == "success" else item
                        for item in results
                    ]
            except Exception:
                # Final safety boundary: adapter/library failures must not escape the job
                # contract or leave successful extraction results falsely marked as complete.
                self._context.logger.exception("Unexpected Tax Invoice Excel output failure")
                results = [
                    _change_result_status(
                        item, "failed", "TAX_INVOICE_EXCEL_OUTPUT_FAILED",
                        "Excel output failed unexpectedly; this document was not written to the workbook.",
                    ) if item.status == "success" else item
                    for item in results
                ]

        successful = sum(item.status == "success" for item in results)
        failed = sum(item.status == "failed" for item in results)
        review = sum(item.status == "review" for item in results)
        if failed == len(results):
            status = "failed"
        elif failed or review:
            status = "completed_with_warnings"
        else:
            status = "completed"
        return JobResult(
            job_id=request.job_id, status=status, total_files=len(results),
            successful_files=successful, failed_files=failed, review_files=review,
            results=tuple(results), output_path=output_path,
        )

    def register_worker(self, worker: object) -> None:
        """Retain active Qt workers so feature unload cannot destroy them mid-run."""
        with self._worker_registry_lock:
            self._active_workers.add(worker)

    def unregister_worker(self, worker: object) -> None:
        with self._worker_registry_lock:
            self._active_workers.discard(worker)

    def shutdown(self) -> None:
        # Wait for complete worker termination before releasing injected service context.
        with self._worker_registry_lock:
            workers = tuple(self._active_workers)
        for worker in workers:
            wait = getattr(worker, "wait", None)
            if callable(wait):
                wait()
        with self._worker_registry_lock:
            self._active_workers.clear()
        with self._execution_lock:
            self._context = None


def _to_plain_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    """Copy nested immutable configuration values into JSON-schema validator input."""
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            result[key] = _to_plain_dict(item)
        elif isinstance(item, tuple):
            result[key] = list(item)
        else:
            result[key] = item
    return result


def _append_warnings_to_successes(
    results: list[FileResult], warnings: tuple[str, ...]
) -> list[FileResult]:
    if not warnings:
        return results
    return [
        FileResult(
            source_path=item.source_path, status=item.status,
            extracted_fields=item.extracted_fields, confidence=item.confidence,
            warnings=tuple(dict.fromkeys(item.warnings + warnings)),
            error_code=item.error_code,
        ) if item.status == "success" else item
        for item in results
    ]


def _change_result_status(
    item: FileResult, status: str, error_code: str | None, warning: str
) -> FileResult:
    return FileResult(
        source_path=item.source_path, status=status,
        extracted_fields=item.extracted_fields, confidence=item.confidence,
        warnings=item.warnings + (warning,), error_code=error_code,
    )
