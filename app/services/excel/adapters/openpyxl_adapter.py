"""openpyxl implementation of the engine-neutral Excel service contract.

The adapter never exposes openpyxl objects, never evaluates formulas, and never
writes to the source workbook. Writes are staged beside the destination, verified,
and promoted with an atomic filesystem replacement.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
import zipfile
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.utils import column_index_from_string
from openpyxl.utils.exceptions import InvalidFileException

from app.core.exceptions import ApplicationError
from app.services.excel.models import (
    ExcelMapping,
    ExcelReadRequest,
    ExcelReadResult,
    ExcelRecord,
    ExcelWriteRequest,
    ExcelWriteResult,
    WorkbookDescriptor,
    WorkbookVerificationResult,
)
from app.services.models import ResourceLimits


class OpenpyxlExcelAdapter:
    """Read and safely update XLSX/XLSM workbooks through public Excel models."""

    _SUPPORTED_SUFFIXES = {".xlsx", ".xlsm"}
    _COLUMN_PATTERN = re.compile(r"^[A-Za-z]{1,3}$")
    _NORMALIZATION_PROFILES = {"exact", "trim", "casefold", "trim_casefold", "remove_whitespace", "remove_whitespace_casefold"}
    _SCALAR_TYPES = (str, int, float, bool, date, datetime, time, Decimal)
    _MAX_ARCHIVE_ENTRIES = 10_000
    _MAX_WORKSHEETS = 256
    _MAX_ROWS = 1_048_576
    _MAX_COLUMNS = 16_384
    _MAX_RECORDS_PER_WRITE = 1_000_000

    def __init__(self, limits: ResourceLimits | None = None) -> None:
        self._limits = limits or ResourceLimits()

    def inspect_workbook(self, path: str) -> WorkbookDescriptor:
        source = self._validated_path(path)
        workbook = self._load(source, read_only=False)
        try:
            warnings = self._workbook_warnings(workbook)
            return WorkbookDescriptor(
                path=str(source),
                worksheets=tuple(workbook.sheetnames),
                file_format=source.suffix.lower().lstrip("."),
                has_macros=source.suffix.lower() == ".xlsm" and workbook.vba_archive is not None,
                warnings=warnings,
            )
        finally:
            workbook.close()

    def read_records(self, request: ExcelReadRequest) -> ExcelReadResult:
        self._validate_read_request(request)
        source = self._validated_path(request.path)
        workbook = self._load(source, read_only=False)
        try:
            worksheet = self._get_worksheet(workbook, request.worksheet)
            columns = tuple(
                (identifier, self._resolve_column(worksheet, identifier, request.header_row))
                for identifier in request.columns
            )
            records: list[ExcelRecord] = []
            for row_number in range(request.data_start_row, worksheet.max_row + 1):
                values = tuple(
                    (identifier, worksheet.cell(row=row_number, column=column_index).value)
                    for identifier, column_index in columns
                )
                if any(value is not None for _, value in values):
                    records.append(ExcelRecord(row_number=row_number, values=values))
            return ExcelReadResult(
                records=tuple(records),
                warnings=self._workbook_warnings(workbook),
            )
        finally:
            workbook.close()

    def write_records(self, request: ExcelWriteRequest) -> ExcelWriteResult:
        self._validate_write_request(request)
        source = self._validated_path(request.source_path)
        destination = self._validated_destination(request.destination_path, source)
        workbook = self._load(source, read_only=False)
        warnings = list(self._workbook_warnings(workbook))
        temporary_path: Path | None = None
        try:
            if request.mapping is None:
                rows_written, write_warnings = self._write_by_row(
                    workbook,
                    request.worksheet,
                    request.records,
                    request.overwrite_policy,
                )
            else:
                rows_written, write_warnings = self._write_by_mapping(
                    workbook, request.records, request.mapping
                )
            warnings.extend(write_warnings)
            if rows_written == 0:
                raise ApplicationError(
                    "EXCEL_NO_ROWS_WRITTEN",
                    "No workbook cells were changed; the output file was not created.",
                    details={"warnings": tuple(warnings)},
                )

            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.stem}.",
                suffix=destination.suffix,
                dir=destination.parent,
            )
            os.close(file_descriptor)
            temporary_path = Path(temporary_name)
            shutil.copy2(source, temporary_path)
            # Save into a staged copy, not the original source workbook.
            workbook.save(temporary_path)
            workbook.close()

            verification = self.verify_output(str(temporary_path))
            warnings.extend(verification.warnings)
            if not verification.valid:
                raise ApplicationError(
                    "EXCEL_OUTPUT_VERIFICATION_FAILED",
                    "The generated workbook failed verification and was not promoted.",
                    details={"errors": verification.errors},
                )
            os.replace(temporary_path, destination)
            temporary_path = None
            return ExcelWriteResult(
                output_path=str(destination),
                rows_written=rows_written,
                warnings=tuple(dict.fromkeys(warnings)),
            )
        except ApplicationError:
            raise
        except (OSError, ValueError, TypeError, InvalidFileException, zipfile.BadZipFile) as exc:
            raise ApplicationError(
                "EXCEL_WRITE_FAILED",
                "The workbook could not be safely written to the requested destination.",
            ) from exc
        finally:
            try:
                workbook.close()
            except (OSError, ValueError):
                pass
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def verify_output(self, path: str) -> WorkbookVerificationResult:
        try:
            source = self._validated_path(path)
            workbook = self._load(source, read_only=False)
            try:
                if not workbook.sheetnames:
                    return WorkbookVerificationResult(
                        valid=False, errors=("The workbook contains no worksheets.",)
                    )
                warnings = self._workbook_warnings(workbook)
                # Force access to dimensions and sheet metadata to detect malformed parts.
                for worksheet in workbook.worksheets:
                    _ = worksheet.max_row, worksheet.max_column
                return WorkbookVerificationResult(valid=True, warnings=warnings)
            finally:
                workbook.close()
        except ApplicationError as exc:
            return WorkbookVerificationResult(valid=False, errors=(exc.code,))
        except (OSError, ValueError, TypeError, InvalidFileException, zipfile.BadZipFile):
            return WorkbookVerificationResult(
                valid=False, errors=("EXCEL_OUTPUT_VERIFICATION_FAILED",)
            )

    def _validated_path(self, path: str) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise ApplicationError("EXCEL_PATH_INVALID", "A valid workbook path is required.")
        source = Path(path).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise ApplicationError("EXCEL_FILE_NOT_FOUND", "The selected workbook does not exist.")
        if source.suffix.lower() not in self._SUPPORTED_SUFFIXES:
            raise ApplicationError(
                "EXCEL_FORMAT_UNSUPPORTED",
                "Only .xlsx and .xlsm workbooks are supported by this adapter.",
            )
        size = source.stat().st_size
        if size <= 0:
            raise ApplicationError("EXCEL_WORKBOOK_CORRUPT", "The workbook file is empty.")
        if size > self._limits.max_file_bytes:
            raise ApplicationError(
                "EXCEL_FILE_SIZE_LIMIT", "The workbook exceeds the configured file-size limit."
            )
        return source

    def _validated_destination(self, path: str, source: Path) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise ApplicationError("EXCEL_DESTINATION_INVALID", "A valid output path is required.")
        destination = Path(path).expanduser().resolve()
        if destination == source:
            raise ApplicationError(
                "EXCEL_SOURCE_OVERWRITE_BLOCKED",
                "The original workbook cannot be used as the output destination.",
            )
        if destination.suffix.lower() != source.suffix.lower():
            raise ApplicationError(
                "EXCEL_DESTINATION_FORMAT_MISMATCH",
                "The output workbook must use the same format as the source workbook.",
            )
        if not destination.parent.exists() or not destination.parent.is_dir():
            raise ApplicationError(
                "EXCEL_DESTINATION_INVALID", "The output directory does not exist."
            )
        return destination

    def _load(self, path: Path, *, read_only: bool):
        self._validate_archive_size(path)
        workbook = None
        try:
            workbook = load_workbook(
                path,
                read_only=read_only,
                data_only=False,
                keep_vba=path.suffix.lower() == ".xlsm",
                keep_links=True,
            )
            if len(workbook.sheetnames) > self._MAX_WORKSHEETS:
                raise ApplicationError(
                    "EXCEL_WORKBOOK_COMPLEXITY_LIMIT",
                    "The workbook contains more worksheets than the adapter allows.",
                )
            for worksheet in workbook.worksheets:
                if (
                    worksheet.max_row > self._MAX_ROWS
                    or worksheet.max_column > self._MAX_COLUMNS
                ):
                    raise ApplicationError(
                        "EXCEL_WORKBOOK_COMPLEXITY_LIMIT",
                        "A worksheet exceeds the supported Excel row or column dimensions.",
                    )
            return workbook
        except ApplicationError:
            if workbook is not None:
                workbook.close()
            raise
        except (OSError, ValueError, InvalidFileException, zipfile.BadZipFile) as exc:
            if workbook is not None:
                workbook.close()
            raise ApplicationError(
                "EXCEL_WORKBOOK_CORRUPT",
                "The workbook is damaged, encrypted, or cannot be opened.",
            ) from exc

    def _validate_archive_size(self, path: Path) -> None:
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > self._MAX_ARCHIVE_ENTRIES:
                    raise ApplicationError(
                        "EXCEL_WORKBOOK_COMPLEXITY_LIMIT",
                        "The workbook contains too many internal archive entries.",
                    )
                expanded_size = sum(item.file_size for item in entries)
                if expanded_size > self._limits.max_file_bytes:
                    raise ApplicationError(
                        "EXCEL_EXPANDED_SIZE_LIMIT",
                        "The expanded workbook contents exceed the configured size limit.",
                    )
                if any(item.flag_bits & 0x1 for item in entries):
                    raise ApplicationError(
                        "EXCEL_WORKBOOK_ENCRYPTED",
                        "Encrypted workbook entries are not supported.",
                    )
        except ApplicationError:
            raise
        except (OSError, zipfile.BadZipFile) as exc:
            raise ApplicationError(
                "EXCEL_WORKBOOK_CORRUPT",
                "The workbook archive is damaged or cannot be inspected.",
            ) from exc

    @staticmethod
    def _get_worksheet(workbook: Any, name: str):
        if not isinstance(name, str) or not name or name not in workbook.sheetnames:
            raise ApplicationError(
                "EXCEL_WORKSHEET_NOT_FOUND", "The configured worksheet does not exist."
            )
        return workbook[name]

    @staticmethod
    def _validate_read_request(request: ExcelReadRequest) -> None:
        if not isinstance(request, ExcelReadRequest):
            raise ApplicationError(
                "EXCEL_REQUEST_INVALID", "A valid Excel read request is required."
            )
        if (
            not isinstance(request.data_start_row, int)
            or isinstance(request.data_start_row, bool)
            or request.data_start_row < 1
            or (request.header_row is not None and (
                not isinstance(request.header_row, int)
                or isinstance(request.header_row, bool)
                or request.header_row < 1
                or request.header_row >= request.data_start_row
            ))
            or not isinstance(request.columns, tuple)
            or not request.columns
            or any(not isinstance(column, str) or not column.strip() for column in request.columns)
        ):
            raise ApplicationError("EXCEL_MAPPING_INVALID", "The Excel read mapping is invalid.")

    @staticmethod
    def _validate_write_request(request: ExcelWriteRequest) -> None:
        if not isinstance(request, ExcelWriteRequest):
            raise ApplicationError(
                "EXCEL_REQUEST_INVALID", "A valid Excel write request is required."
            )
        if (
            not isinstance(request.records, tuple)
            or not request.records
            or len(request.records) > OpenpyxlExcelAdapter._MAX_RECORDS_PER_WRITE
            or request.overwrite_policy not in {"empty_only", "overwrite", "review"}
            or not isinstance(request.worksheet, str)
            or not request.worksheet
        ):
            raise ApplicationError("EXCEL_MAPPING_INVALID", "The Excel write request is invalid.")
        if request.mapping is not None:
            OpenpyxlExcelAdapter._validate_mapping(request.mapping)
            if request.worksheet != request.mapping.worksheet:
                raise ApplicationError(
                    "EXCEL_MAPPING_INVALID",
                    "The write request worksheet must match the configured mapping worksheet.",
                )

    @staticmethod
    def _validate_mapping(mapping: ExcelMapping) -> None:
        if not isinstance(mapping, ExcelMapping):
            raise ApplicationError("EXCEL_MAPPING_INVALID", "A valid Excel mapping is required.")
        if (
            not isinstance(mapping.worksheet, str)
            or not mapping.worksheet
            or not isinstance(mapping.source_key_column, str)
            or not mapping.source_key_column
            or not isinstance(mapping.target_column, str)
            or not mapping.target_column
            or not isinstance(mapping.data_start_row, int)
            or isinstance(mapping.data_start_row, bool)
            or mapping.data_start_row < 1
            or (
                mapping.header_row is not None
                and (
                    not isinstance(mapping.header_row, int)
                    or isinstance(mapping.header_row, bool)
                    or mapping.header_row < 1
                    or mapping.header_row >= mapping.data_start_row
                )
            )
            or not mapping.source_key_column
            or not mapping.target_column
            or mapping.key_type not in {"text", "number"}
            or mapping.normalization_profile not in OpenpyxlExcelAdapter._NORMALIZATION_PROFILES
            or mapping.duplicate_policy not in {"reject", "review", "first", "all"}
            or mapping.unmatched_policy not in {"report", "skip", "fail"}
            or mapping.overwrite_policy not in {"empty_only", "overwrite", "review"}
        ):
            raise ApplicationError(
                "EXCEL_MAPPING_INVALID", "The configured Excel mapping is invalid."
            )

    def _resolve_column(self, worksheet: Any, identifier: str, header_row: int | None) -> int:
        if header_row is not None:
            matches = [
                cell.column
                for cell in worksheet[header_row]
                if isinstance(cell.value, str) and cell.value == identifier
            ]
            if len(matches) > 1:
                raise ApplicationError(
                    "EXCEL_HEADER_DUPLICATE",
                    "A configured column header appears more than once in the worksheet.",
                    details={"header": identifier},
                )
            if matches:
                return matches[0]
        if not self._COLUMN_PATTERN.fullmatch(identifier):
            raise ApplicationError(
                "EXCEL_COLUMN_NOT_FOUND",
                "A configured column header or Excel column letter could not be resolved.",
                details={"column": identifier},
            )
        try:
            return column_index_from_string(identifier.upper())
        except ValueError as exc:
            raise ApplicationError(
                "EXCEL_MAPPING_INVALID", "The configured Excel column reference is invalid."
            ) from exc

    def _write_by_row(
        self, workbook: Any, worksheet_name: str, records: tuple[ExcelRecord, ...], policy: str
    ) -> tuple[int, tuple[str, ...]]:
        worksheet = self._get_worksheet(workbook, worksheet_name)
        warnings: list[str] = []
        written_rows: set[int] = set()
        for record in records:
            if (
                not isinstance(record, ExcelRecord)
                or not isinstance(record.row_number, int)
                or isinstance(record.row_number, bool)
                or record.row_number < 1
                or record.row_number > self._MAX_ROWS
                or not isinstance(record.values, tuple)
                or not record.values
            ):
                raise ApplicationError("EXCEL_MAPPING_INVALID", "An Excel record is invalid.")
            for column, value in record.values:
                column_index = self._resolve_column(worksheet, column, None)
                cell = worksheet.cell(row=record.row_number, column=column_index)
                if cell.value not in (None, ""):
                    if policy == "empty_only":
                        warnings.append(f"Existing value at {cell.coordinate} was preserved.")
                        continue
                    if policy == "review":
                        warnings.append(f"Existing value at {cell.coordinate} requires review.")
                        continue
                self._set_literal_or_scalar(cell, value)
                written_rows.add(record.row_number)
        return len(written_rows), tuple(warnings)

    def _write_by_mapping(
        self, workbook: Any, records: tuple[ExcelRecord, ...], mapping: ExcelMapping
    ) -> tuple[int, tuple[str, ...]]:
        worksheet = self._get_worksheet(workbook, mapping.worksheet)
        key_column = self._resolve_column(worksheet, mapping.source_key_column, mapping.header_row)
        target_column = self._resolve_column(worksheet, mapping.target_column, mapping.header_row)
        source_rows: dict[str, list[int]] = {}
        warnings: list[str] = []
        for row_number in range(mapping.data_start_row, worksheet.max_row + 1):
            raw_key = worksheet.cell(row=row_number, column=key_column).value
            if raw_key in (None, ""):
                continue
            key = self._normalize_key(raw_key, mapping)
            source_rows.setdefault(key, []).append(row_number)

        duplicate_source = {key: rows for key, rows in source_rows.items() if len(rows) > 1}
        if duplicate_source and mapping.duplicate_policy == "reject":
            raise ApplicationError(
                "EXCEL_DUPLICATE_KEY",
                "Duplicate source keys were found in the configured worksheet.",
                details={"duplicate_count": len(duplicate_source)},
            )
        if duplicate_source and mapping.duplicate_policy == "review":
            warnings.append(
                f"{len(duplicate_source)} duplicate source key(s) were skipped for manual review."
            )

        incoming: dict[str, list[object]] = {}
        for record in records:
            if (
                not isinstance(record, ExcelRecord)
                or not isinstance(record.row_number, int)
                or isinstance(record.row_number, bool)
                or record.row_number < 1
            ):
                raise ApplicationError("EXCEL_MAPPING_INVALID", "An Excel record is invalid.")
            values = dict(record.values)
            if mapping.source_key_column not in values or mapping.target_column not in values:
                raise ApplicationError(
                    "EXCEL_MAPPING_INVALID",
                    "Each extracted record must contain the configured key and target fields.",
                )
            key = self._normalize_key(values[mapping.source_key_column], mapping)
            incoming.setdefault(key, []).append(values[mapping.target_column])

        duplicate_incoming = {key: values for key, values in incoming.items() if len(values) > 1}
        if duplicate_incoming and mapping.duplicate_policy == "reject":
            raise ApplicationError(
                "EXCEL_DUPLICATE_KEY",
                "Duplicate extracted keys were found in the input records.",
                details={"duplicate_count": len(duplicate_incoming)},
            )
        if duplicate_incoming and mapping.duplicate_policy == "review":
            warnings.append(
                (
                    f"{len(duplicate_incoming)} duplicate extracted key(s) " 
                    "were skipped for manual review."
                )
            )

        rows_written = 0
        for key, values in incoming.items():
            matching_rows = source_rows.get(key, [])
            if not matching_rows:
                if mapping.unmatched_policy == "fail":
                    raise ApplicationError(
                        "EXCEL_KEY_NOT_FOUND",
                        "An extracted key does not exist in the configured source worksheet.",
                    )
                if mapping.unmatched_policy == "report":
                    warnings.append("One or more extracted keys were not found in the workbook.")
                continue
            if key in duplicate_source and mapping.duplicate_policy == "review":
                continue
            if len(values) > 1 and mapping.duplicate_policy == "review":
                continue
            if mapping.duplicate_policy == "first":
                matching_rows = matching_rows[:1]
                values = values[:1]
            elif mapping.duplicate_policy == "all":
                if len(values) == 1:
                    values = values * len(matching_rows)
                elif len(values) != len(matching_rows):
                    raise ApplicationError(
                        "EXCEL_DUPLICATE_KEY",
                        "The number of duplicate extracted records does not match " 
                        "the duplicate workbook rows.",
                        details={"source_rows": len(matching_rows), "input_records": len(values)},
                    )
            else:
                values = values[:1]
            for row_number, value in zip(matching_rows, values, strict=True):
                cell = worksheet.cell(row=row_number, column=target_column)
                if cell.value not in (None, ""):
                    if mapping.overwrite_policy == "empty_only":
                        warnings.append(f"Existing value at {cell.coordinate} was preserved.")
                        continue
                    if mapping.overwrite_policy == "review":
                        warnings.append(f"Existing value at {cell.coordinate} requires review.")
                        continue
                self._set_literal_or_scalar(cell, value)
                rows_written += 1
        return rows_written, tuple(warnings)

    @staticmethod
    def _normalize_key(value: object, mapping: ExcelMapping) -> str:
        if value is None or isinstance(value, bool):
            raise ApplicationError("EXCEL_MAPPING_INVALID", "A source key is blank or invalid.")
        if mapping.key_type == "number":
            try:
                number = Decimal(str(value).strip())
                if not number.is_finite():
                    raise InvalidOperation
                return format(number.normalize(), "f")
            except (InvalidOperation, ValueError) as exc:
                raise ApplicationError(
                    "EXCEL_MAPPING_INVALID", "A numeric key could not be normalized."
                ) from exc
        normalized = str(value)
        profile = mapping.normalization_profile
        if profile in {"trim", "trim_casefold"}:
            normalized = normalized.strip()
        if profile in {"remove_whitespace", "remove_whitespace_casefold"}:
            normalized = "".join(normalized.split())
        if profile in {"casefold", "trim_casefold", "remove_whitespace_casefold"}:
            normalized = normalized.casefold()
        return normalized

    @classmethod
    def _set_literal_or_scalar(cls, cell: Cell, value: object) -> None:
        if value is not None and not isinstance(value, cls._SCALAR_TYPES):
            raise ApplicationError(
                "EXCEL_VALUE_UNSUPPORTED", "An extracted value has an unsupported data type."
            )
        if isinstance(value, float) and not math.isfinite(value):
            raise ApplicationError(
                "EXCEL_VALUE_UNSUPPORTED", "Non-finite numeric values are not supported."
            )
        cell.value = value
        # openpyxl treats strings beginning with '=' as formulas; keep document data literal.
        if isinstance(value, str):
            cell.data_type = "s"

    @staticmethod
    def _workbook_warnings(workbook: Any) -> tuple[str, ...]:
        warnings: list[str] = []
        if getattr(workbook, "_external_links", None):
            warnings.append("Workbook contains external links; verify link behavior after editing.")
        for worksheet in workbook.worksheets:
            if getattr(worksheet, "_pivots", None):
                warnings.append(
                    "Workbook contains pivot tables that may not survive an openpyxl round-trip."
                )
            if getattr(worksheet, "_charts", None) or getattr(worksheet, "_images", None):
                warnings.append(
                    "Workbook contains charts or images; drawing preservation is not guaranteed."
                )
        if getattr(workbook, "vba_archive", None) is not None:
            warnings.append(
                "VBA content is retained where supported; macro signatures may be invalidated."
            )
        if any(
            cell.data_type == "f"
            for worksheet in workbook.worksheets
            for cell in worksheet._cells.values()
        ):
            warnings.append(
                "Formula expressions are retained but not calculated; "
                "cached results may be unavailable."
            )
        return tuple(dict.fromkeys(warnings))
