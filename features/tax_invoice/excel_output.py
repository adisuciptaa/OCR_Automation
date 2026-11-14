"""Tax Invoice feature mapping from validated extraction results to Excel."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.exceptions import ApplicationError
from app.core.job_contracts import FileResult
from app.services.excel.models import (
    ExcelMapping,
    ExcelReadRequest,
    ExcelRecord,
    ExcelWriteRequest,
)

_ALLOWED_FIELDS = {"tax_invoice_number", "invoice_number"}


def write_validated_results(
    excel_service: Any,
    *,
    results: tuple[FileResult, ...],
    configuration: Mapping[str, Any],
    destination_path: str,
) -> tuple[tuple[FileResult, ...], str | None, tuple[str, ...]]:
    """Write only successful documents; review, failed, and skipped are excluded.

    The source workbook is configured separately from JobRequest.output_path. The latter
    is always the new output destination, preserving the original workbook.
    """
    eligible = [item for item in results if item.status == "success"]
    if not eligible:
        return results, None, ("EXCEL_NO_ELIGIBLE_SUCCESS_RESULTS",)

    match_field = str(configuration["match_field"])
    write_field = str(configuration["write_field"])
    if match_field not in _ALLOWED_FIELDS or write_field not in _ALLOWED_FIELDS or match_field == write_field:
        raise ApplicationError(
            "EXCEL_MAPPING_INVALID",
            "The Excel match field and write field must be different supported Tax Invoice fields.",
        )

    source_path = str(configuration["source_workbook_path"])
    worksheet = str(configuration["worksheet"])
    source_key_column = str(configuration["source_key_column"])
    target_column = str(configuration["target_column"])
    header_row = configuration.get("header_row")
    header_row = int(header_row) if header_row is not None else None
    data_start_row = int(configuration["data_start_row"])
    key_type = str(configuration.get("key_type", "text"))
    normalization_profile = str(
        configuration.get("normalization_profile")
        or ("remove_whitespace" if match_field == "invoice_number" else "exact")
    )
    duplicate_policy = str(configuration.get("duplicate_policy", "review"))
    unmatched_policy = str(configuration.get("unmatched_policy", "report"))
    overwrite_policy = str(configuration.get("overwrite_policy", "empty_only"))

    mapping = ExcelMapping(
        worksheet=worksheet,
        header_row=header_row,
        data_start_row=data_start_row,
        source_key_column=source_key_column,
        target_column=target_column,
        key_type=key_type,  # type: ignore[arg-type]
        normalization_profile=normalization_profile,
        duplicate_policy=duplicate_policy,  # type: ignore[arg-type]
        unmatched_policy=unmatched_policy,  # type: ignore[arg-type]
        overwrite_policy=overwrite_policy,  # type: ignore[arg-type]
    )

    descriptor = excel_service.inspect_workbook(source_path)
    if worksheet not in descriptor.worksheets:
        raise ApplicationError(
            "EXCEL_WORKSHEET_NOT_FOUND",
            "The configured worksheet does not exist in the source workbook.",
        )
    # Preflight header/column resolution via the public service before attempting a write.
    read_result = excel_service.read_records(
        ExcelReadRequest(
            path=source_path,
            worksheet=worksheet,
            header_row=header_row,
            data_start_row=data_start_row,
            columns=(source_key_column, target_column),
        )
    )

    records: list[ExcelRecord] = []
    updated_results = list(results)
    warnings = list(descriptor.warnings) + list(read_result.warnings)
    for index, item in enumerate(updated_results):
        # This explicit gate is the safety boundary: no non-success item reaches Excel.
        if item.status != "success":
            continue
        fields = item.extracted_fields
        key_payload = fields.get(match_field)
        value_payload = fields.get(write_field)
        key = _normalized_field(key_payload)
        value = _normalized_field(value_payload)
        if not key or not value:
            updated_results[index] = _with_status(
                item,
                "review",
                "EXCEL_REQUIRED_IDENTIFIER_MISSING",
                "EXCEL_REQUIRED_IDENTIFIER_MISSING: a validated identifier required for Excel mapping is missing.",
            )
            continue
        records.append(
            ExcelRecord(
                row_number=1,
                values=((source_key_column, key), (target_column, value)),
            )
        )

    if not records:
        return tuple(updated_results), None, tuple(dict.fromkeys(warnings + ["EXCEL_NO_ELIGIBLE_SUCCESS_RESULTS"]))

    write_result = excel_service.write_records(
        ExcelWriteRequest(
            source_path=source_path,
            destination_path=destination_path,
            worksheet=worksheet,
            records=tuple(records),
            overwrite_policy=overwrite_policy,  # type: ignore[arg-type]
            mapping=mapping,
        )
    )
    warnings.extend(write_result.warnings)
    if write_result.rows_written == 0:
        warnings.append("EXCEL_NO_ROWS_WRITTEN")
        return tuple(updated_results), None, tuple(dict.fromkeys(warnings))
    return tuple(updated_results), write_result.output_path, tuple(dict.fromkeys(warnings))


def _normalized_field(payload: object) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    value = payload.get("normalized_value")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None



def _with_status(
    result: FileResult, status: str, error_code: str, warning: str
) -> FileResult:
    return FileResult(
        source_path=result.source_path,
        status=status,
        extracted_fields=result.extracted_fields,
        confidence=result.confidence,
        warnings=result.warnings + (warning,),
        error_code=error_code if status == "failed" else None,
    )
