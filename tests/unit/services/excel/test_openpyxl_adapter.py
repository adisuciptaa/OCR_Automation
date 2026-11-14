from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from app.core.exceptions import ApplicationError
from app.services.excel.adapters import OpenpyxlExcelAdapter
from app.services.excel.models import (
    ExcelMapping,
    ExcelReadRequest,
    ExcelRecord,
    ExcelWriteRequest,
)


@pytest.fixture
def workbook_path(tmp_path: Path) -> Path:
    path = tmp_path / "source.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Invoices"
    sheet.append(["Invoice ID", "Amount", "Status"])
    sheet.append(["000123", 100, None])
    sheet.append(["000124", 200, "Paid"])
    sheet["B2"].number_format = '"$"#,##0.00'
    sheet["B3"] = "=SUM(100,100)"
    workbook.create_sheet("Notes")
    workbook.save(path)
    return path


def test_inspect_workbook_returns_sheet_metadata(workbook_path: Path) -> None:
    descriptor = OpenpyxlExcelAdapter().inspect_workbook(str(workbook_path))
    assert descriptor.worksheets == ("Invoices", "Notes")
    assert descriptor.file_format == "xlsx"
    assert descriptor.has_macros is False


def test_read_records_resolves_headers_and_preserves_identifier_text(workbook_path: Path) -> None:
    result = OpenpyxlExcelAdapter().read_records(
        ExcelReadRequest(
            path=str(workbook_path),
            worksheet="Invoices",
            header_row=1,
            data_start_row=2,
            columns=("Invoice ID", "Amount"),
        )
    )
    assert len(result.records) == 2
    assert dict(result.records[0].values) == {"Invoice ID": "000123", "Amount": 100}
    assert result.records[0].row_number == 2


def test_write_records_uses_temp_copy_and_preserves_source(
    workbook_path: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "result.xlsx"
    adapter = OpenpyxlExcelAdapter()
    result = adapter.write_records(
        ExcelWriteRequest(
            source_path=str(workbook_path),
            destination_path=str(destination),
            worksheet="Invoices",
            records=(ExcelRecord(row_number=2, values=(("C", "Reviewed"),)),),
        )
    )
    assert result.rows_written == 1
    assert destination.exists()
    source_book = load_workbook(workbook_path, data_only=False)
    output_book = load_workbook(destination, data_only=False)
    assert source_book["Invoices"]["C2"].value is None
    assert output_book["Invoices"]["C2"].value == "Reviewed"
    assert output_book["Invoices"]["B3"].value == "=SUM(100,100)"
    assert output_book.sheetnames == ["Invoices", "Notes"]
    assert output_book["Invoices"]["B2"].number_format == '"$"#,##0.00'




def test_rows_written_counts_distinct_rows_not_cells(workbook_path: Path, tmp_path: Path) -> None:
    destination = tmp_path / "multi-cell.xlsx"
    result = OpenpyxlExcelAdapter().write_records(
        ExcelWriteRequest(
            source_path=str(workbook_path),
            destination_path=str(destination),
            worksheet="Invoices",
            records=(
                ExcelRecord(2, (("C", "Reviewed"), ("B", 150))),
            ),
            overwrite_policy="overwrite",
        )
    )
    assert result.rows_written == 1

def test_mapping_write_matches_text_keys_and_preserves_leading_zeroes(
    workbook_path: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "mapped.xlsx"
    mapping = ExcelMapping(
        worksheet="Invoices",
        header_row=1,
        data_start_row=2,
        source_key_column="Invoice ID",
        target_column="Status",
        key_type="text",
        normalization_profile="trim",
        duplicate_policy="reject",
        unmatched_policy="fail",
        overwrite_policy="empty_only",
    )
    result = OpenpyxlExcelAdapter().write_records(
        ExcelWriteRequest(
            source_path=str(workbook_path),
            destination_path=str(destination),
            worksheet="Invoices",
            records=(
                ExcelRecord(
                    row_number=1,
                    values=(("Invoice ID", " 000123 "), ("Status", "Matched")),
                ),
            ),
            mapping=mapping,
        )
    )
    assert result.rows_written == 1
    output = load_workbook(destination)
    assert output["Invoices"]["C2"].value == "Matched"
    assert output["Invoices"]["C3"].value == "Paid"


def test_duplicate_source_keys_are_rejected(workbook_path: Path, tmp_path: Path) -> None:
    workbook = load_workbook(workbook_path)
    workbook["Invoices"]["A3"] = "000123"
    workbook.save(workbook_path)
    mapping = ExcelMapping(
        worksheet="Invoices", header_row=1, data_start_row=2,
        source_key_column="Invoice ID", target_column="Status",
        duplicate_policy="reject",
    )
    with pytest.raises(ApplicationError) as error:
        OpenpyxlExcelAdapter().write_records(
            ExcelWriteRequest(
                source_path=str(workbook_path),
                destination_path=str(tmp_path / "out.xlsx"),
                worksheet="Invoices",
                records=(ExcelRecord(1, (("Invoice ID", "000123"), ("Status", "X"))),),
                mapping=mapping,
            )
        )
    assert error.value.code == "EXCEL_DUPLICATE_KEY"


def test_unmatched_key_can_fail_without_creating_output(
    workbook_path: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "out.xlsx"
    mapping = ExcelMapping(
        worksheet="Invoices", header_row=1, data_start_row=2,
        source_key_column="Invoice ID", target_column="Status",
        unmatched_policy="fail",
    )
    with pytest.raises(ApplicationError) as error:
        OpenpyxlExcelAdapter().write_records(
            ExcelWriteRequest(
                source_path=str(workbook_path),
                destination_path=str(destination),
                worksheet="Invoices",
                records=(ExcelRecord(1, (("Invoice ID", "missing"), ("Status", "X"))),),
                mapping=mapping,
            )
        )
    assert error.value.code == "EXCEL_KEY_NOT_FOUND"
    assert not destination.exists()


def test_formula_like_input_is_written_as_literal_text(workbook_path: Path, tmp_path: Path) -> None:
    destination = tmp_path / "literal.xlsx"
    OpenpyxlExcelAdapter().write_records(
        ExcelWriteRequest(
            source_path=str(workbook_path),
            destination_path=str(destination),
            worksheet="Invoices",
            records=(ExcelRecord(2, (("C", '=HYPERLINK("https://bad.example","click")'),)),),
        )
    )
    output = load_workbook(destination, data_only=False)
    cell = output["Invoices"]["C2"]
    assert cell.value.startswith("=")
    assert cell.data_type == "s"


def test_original_workbook_cannot_be_destination(workbook_path: Path) -> None:
    with pytest.raises(ApplicationError) as error:
        OpenpyxlExcelAdapter().write_records(
            ExcelWriteRequest(
                source_path=str(workbook_path),
                destination_path=str(workbook_path),
                worksheet="Invoices",
                records=(ExcelRecord(2, (("C", "X"),)),),
            )
        )
    assert error.value.code == "EXCEL_SOURCE_OVERWRITE_BLOCKED"


def test_verify_output_rejects_corrupt_workbook(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.xlsx"
    corrupt.write_text("not a zip workbook")
    result = OpenpyxlExcelAdapter().verify_output(str(corrupt))
    assert result.valid is False


def test_overwrite_review_preserves_existing_target(workbook_path: Path, tmp_path: Path) -> None:
    destination = tmp_path / "review.xlsx"
    mapping = ExcelMapping(
        worksheet="Invoices", header_row=1, data_start_row=2,
        source_key_column="Invoice ID", target_column="Status",
        overwrite_policy="review",
    )
    with pytest.raises(ApplicationError) as error:
        OpenpyxlExcelAdapter().write_records(
            ExcelWriteRequest(
                source_path=str(workbook_path), destination_path=str(destination),
                worksheet="Invoices",
                records=(ExcelRecord(1, (("Invoice ID", "000124"), ("Status", "Changed"))),),
                mapping=mapping,
            )
        )
    assert error.value.code == "EXCEL_NO_ROWS_WRITTEN"
    assert not destination.exists()


def test_all_duplicate_policy_updates_all_matching_source_rows(
    workbook_path: Path, tmp_path: Path
) -> None:
    workbook = load_workbook(workbook_path)
    workbook["Invoices"]["A3"] = "000123"
    workbook.save(workbook_path)
    destination = tmp_path / "all.xlsx"
    mapping = ExcelMapping(
        worksheet="Invoices", header_row=1, data_start_row=2,
        source_key_column="Invoice ID", target_column="Status",
        duplicate_policy="all",
        overwrite_policy="overwrite",
    )
    result = OpenpyxlExcelAdapter().write_records(
        ExcelWriteRequest(
            source_path=str(workbook_path), destination_path=str(destination),
            worksheet="Invoices",
            records=(ExcelRecord(1, (("Invoice ID", "000123"), ("Status", "Matched"))),),
            mapping=mapping,
        )
    )
    output = load_workbook(destination)
    assert result.rows_written == 2
    assert output["Invoices"]["C2"].value == "Matched"
    assert output["Invoices"]["C3"].value == "Matched"


def test_unsupported_workbook_extension_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "legacy.xls"
    source.write_bytes(b"legacy")
    with pytest.raises(ApplicationError) as error:
        OpenpyxlExcelAdapter().inspect_workbook(str(source))
    assert error.value.code == "EXCEL_FORMAT_UNSUPPORTED"


def test_mapping_can_remove_all_whitespace_from_invoice_keys(
    tmp_path: Path,
) -> None:
    source = tmp_path / "invoice-source.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Invoices"
    sheet.append(["Invoice Number", "Tax Invoice Number"])
    sheet.append(["INV 2026 / 001", None])
    workbook.save(source)
    destination = tmp_path / "invoice-output.xlsx"
    mapping = ExcelMapping(
        worksheet="Invoices",
        header_row=1,
        data_start_row=2,
        source_key_column="Invoice Number",
        target_column="Tax Invoice Number",
        normalization_profile="remove_whitespace",
        duplicate_policy="reject",
        unmatched_policy="fail",
    )

    result = OpenpyxlExcelAdapter().write_records(
        ExcelWriteRequest(
            source_path=str(source),
            destination_path=str(destination),
            worksheet="Invoices",
            records=(ExcelRecord(1, (("Invoice Number", "INV2026/001"), ("Tax Invoice Number", "010.000-24.12345678"))),),
            mapping=mapping,
        )
    )

    output = load_workbook(destination)
    assert result.rows_written == 1
    assert output["Invoices"]["B2"].value == "010.000-24.12345678"
    assert load_workbook(source)["Invoices"]["B2"].value is None
