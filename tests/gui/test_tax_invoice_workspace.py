"""PySide6 offscreen smoke and presentation-contract tests for Tax Invoice UI."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.core.job_contracts import FileResult, JobResult
from features.tax_invoice.ui import TaxInvoiceWorkspace


@pytest.fixture(scope="module")
def qapplication() -> QApplication:
    application = QApplication.instance()
    if application is None:
        application = QApplication(["tax-invoice-workspace-tests"])
    return application


def test_workspace_constructs_with_excel_disabled_and_empty_result_table(qapplication):
    workspace = TaxInvoiceWorkspace(feature=object(), actor_id="test-operator")

    assert workspace.windowTitle() == ""
    assert workspace.input_summary.text() == "Belum ada PDF dipilih"
    assert workspace.excel_enabled.isChecked() is False
    assert workspace.source_workbook_edit.isEnabled() is False
    assert workspace.results_table.rowCount() == 0
    assert workspace.success_count[1].text() == "0"
    assert workspace.review_count[1].text() == "0"
    assert workspace.failed_count[1].text() == "0"

    workspace.close()
    workspace.deleteLater()
    qapplication.processEvents()


def test_workspace_projects_internal_results_into_exact_three_user_statuses(qapplication):
    workspace = TaxInvoiceWorkspace(feature=object(), actor_id="test-operator")
    result = JobResult(
        job_id="job-gui-test",
        status="completed_with_warnings",
        total_files=4,
        successful_files=1,
        failed_files=1,
        review_files=1,
        results=(
            FileResult("success.pdf", "success", {}, {}, ()),
            FileResult("review.pdf", "review", {}, {}, ("Check identifier",)),
            FileResult("failed.pdf", "failed", {}, {}, (), "PDF_CORRUPT"),
            FileResult("skipped.pdf", "skipped", {}, {}, ("Skipped by policy",)),
        ),
        output_path=None,
    )

    workspace._on_job_completed(result)

    assert workspace.success_count[1].text() == "1"
    assert workspace.review_count[1].text() == "2"
    assert workspace.failed_count[1].text() == "1"
    assert [workspace.results_table.item(row, 1).text() for row in range(4)] == [
        "Success", "Need Review", "Failed", "Need Review",
    ]
    assert "1 Success" in workspace.status_message.text()
    assert "2 Need Review" in workspace.status_message.text()
    assert "1 Failed" in workspace.status_message.text()

    workspace.close()
    workspace.deleteLater()
    qapplication.processEvents()
