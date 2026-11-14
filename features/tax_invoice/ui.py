"""PySide6 workspace for the Tax Invoice feature.

The workspace owns presentation state only. OCR, validation, and Excel output are
executed by the feature runtime on a dedicated worker thread.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Mapping

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.job_contracts import JobRequest, JobResult
from features.tax_invoice.config import default_configuration

LOGGER = logging.getLogger(__name__)
_STATUS_LABELS = {"success": "Success", "review": "Need Review", "failed": "Failed", "skipped": "Need Review"}


class _TaxInvoiceJobWorker(QThread):
    """Runs the feature's synchronous workflow away from the GUI thread."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, feature: object, request: JobRequest) -> None:
        super().__init__()
        self._feature = feature
        self._request = request

    def run(self) -> None:
        try:
            result = self._feature.execute(self._request)
            self.completed.emit(result)
        except Exception:
            LOGGER.exception("Tax Invoice workspace job failed unexpectedly")
            self.failed.emit("Processing could not be completed. Check the application log for details.")


class TaxInvoiceWorkspace(QWidget):
    """User workspace for PDF input, processing options, Excel mapping, and results."""

    def __init__(self, *, feature: object, actor_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._feature = feature
        self._actor_id = actor_id
        self._input_paths: list[str] = []
        self._worker: _TaxInvoiceJobWorker | None = None
        self._last_result: JobResult | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        heading = QLabel("Pembacaan Faktur Pajak")
        heading.setObjectName("pageTitle")
        subtitle = QLabel("Pilih dokumen PDF, atur proses OCR, dan tinjau hasil ekstraksi.")
        subtitle.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(subtitle)

        input_group = QGroupBox("Dokumen input")
        input_layout = QVBoxLayout(input_group)
        input_row = QHBoxLayout()
        self.input_summary = QLabel("Belum ada PDF dipilih")
        self.input_summary.setWordWrap(True)
        self.add_files_button = QPushButton("Pilih PDF")
        self.add_files_button.clicked.connect(self._choose_pdfs)
        self.clear_files_button = QPushButton("Hapus pilihan")
        self.clear_files_button.clicked.connect(self._clear_pdfs)
        input_row.addWidget(self.input_summary, 1)
        input_row.addWidget(self.add_files_button)
        input_row.addWidget(self.clear_files_button)
        input_layout.addLayout(input_row)
        root.addWidget(input_group)

        options = QSplitter()
        processing_group = QGroupBox("Pengaturan pemrosesan")
        processing_form = QFormLayout(processing_group)
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(100, 400)
        self.dpi_spin.setValue(200)
        self.max_pages_spin = QSpinBox()
        self.max_pages_spin.setRange(1, 5000)
        self.max_pages_spin.setValue(200)
        self.top_ratio_spin = QDoubleSpinBox()
        self.top_ratio_spin.setRange(0.05, 0.75)
        self.top_ratio_spin.setSingleStep(0.05)
        self.top_ratio_spin.setDecimals(2)
        self.top_ratio_spin.setValue(0.25)
        self.fallback_check = QCheckBox("Periksa seluruh halaman jika marker tidak ditemukan")
        self.prefer_embedded_check = QCheckBox("Utamakan teks tertanam PDF")
        self.prefer_embedded_check.setChecked(True)
        self.language_edit = QLineEdit("ind+eng")
        processing_form.addRow("Render DPI", self.dpi_spin)
        processing_form.addRow("Maks. halaman per PDF", self.max_pages_spin)
        processing_form.addRow("Area deteksi atas", self.top_ratio_spin)
        processing_form.addRow("", self.fallback_check)
        processing_form.addRow("", self.prefer_embedded_check)
        processing_form.addRow("Bahasa OCR", self.language_edit)
        options.addWidget(processing_group)

        excel_group = QGroupBox("Pemetaan Excel (opsional)")
        excel_form = QFormLayout(excel_group)
        self.excel_enabled = QCheckBox("Aktifkan pencocokan dan output Excel")
        self.excel_enabled.toggled.connect(self._set_excel_enabled)
        self.source_workbook_edit = QLineEdit()
        self.source_workbook_edit.setPlaceholderText("Pilih workbook sumber (.xlsx)")
        source_row = QHBoxLayout()
        source_row.addWidget(self.source_workbook_edit, 1)
        self.source_workbook_button = QPushButton("Browse")
        self.source_workbook_button.clicked.connect(self._choose_source_workbook)
        source_row.addWidget(self.source_workbook_button)
        self.worksheet_edit = QLineEdit("Sheet1")
        self.header_row_spin = QSpinBox()
        self.header_row_spin.setRange(1, 10000)
        self.header_row_spin.setValue(1)
        self.data_row_spin = QSpinBox()
        self.data_row_spin.setRange(1, 1000000)
        self.data_row_spin.setValue(2)
        self.source_key_edit = QLineEdit("Invoice Number")
        self.target_column_edit = QLineEdit("Tax Invoice Number")
        self.match_field_combo = QComboBox()
        self.match_field_combo.addItem("Invoice Number", "invoice_number")
        self.match_field_combo.addItem("Tax Invoice Number", "tax_invoice_number")
        self.write_field_combo = QComboBox()
        self.write_field_combo.addItem("Tax Invoice Number", "tax_invoice_number")
        self.write_field_combo.addItem("Invoice Number", "invoice_number")
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Lokasi file hasil; workbook sumber tidak diubah")
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_edit, 1)
        self.output_button = QPushButton("Browse")
        self.output_button.clicked.connect(self._choose_output_workbook)
        output_row.addWidget(self.output_button)
        excel_form.addRow("", self.excel_enabled)
        excel_form.addRow("Workbook sumber", self._wrap_layout(source_row))
        excel_form.addRow("Worksheet", self.worksheet_edit)
        excel_form.addRow("Header row", self.header_row_spin)
        excel_form.addRow("Data mulai row", self.data_row_spin)
        excel_form.addRow("Kolom kunci sumber", self.source_key_edit)
        excel_form.addRow("Kolom target", self.target_column_edit)
        excel_form.addRow("Field pencocokan", self.match_field_combo)
        excel_form.addRow("Field yang ditulis", self.write_field_combo)
        excel_form.addRow("File output", self._wrap_layout(output_row))
        options.addWidget(excel_group)
        options.setSizes([420, 620])
        root.addWidget(options)
        self._set_excel_enabled(False)

        action_row = QHBoxLayout()
        self.run_button = QPushButton("Mulai proses")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self._start_job)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.status_message = QLabel("Siap")
        action_row.addWidget(self.run_button)
        action_row.addWidget(self.progress, 1)
        action_row.addWidget(self.status_message, 1)
        root.addLayout(action_row)

        summary = QGridLayout()
        self.success_count = self._summary_card("Success", "0")
        self.review_count = self._summary_card("Need Review", "0")
        self.failed_count = self._summary_card("Failed", "0")
        summary.addWidget(self.success_count[0], 0, 0)
        summary.addWidget(self.review_count[0], 0, 1)
        summary.addWidget(self.failed_count[0], 0, 2)
        root.addLayout(summary)

        results_group = QGroupBox("Hasil dokumen")
        results_layout = QVBoxLayout(results_group)
        self.results_table = QTableWidget(0, 4)
        self.results_table.setHorizontalHeaderLabels(["Dokumen", "Status", "Confidence", "Keterangan"])
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.itemSelectionChanged.connect(self._show_selected_details)
        results_layout.addWidget(self.results_table)
        self.details = QLabel("Pilih baris hasil untuk melihat detail ekstraksi dan catatan.")
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(self.details.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
        results_layout.addWidget(self.details)
        root.addWidget(results_group, 1)

    @staticmethod
    def _wrap_layout(layout: QHBoxLayout) -> QWidget:
        wrapper = QWidget()
        wrapper.setLayout(layout)
        return wrapper

    @staticmethod
    def _summary_card(label: str, value: str) -> tuple[QGroupBox, QLabel]:
        card = QGroupBox(label)
        layout = QVBoxLayout(card)
        count = QLabel(value)
        count.setObjectName("summaryCount")
        layout.addWidget(count)
        return card, count

    def _set_excel_enabled(self, enabled: bool) -> None:
        for widget in (
            self.source_workbook_edit, self.source_workbook_button, self.worksheet_edit,
            self.header_row_spin, self.data_row_spin, self.source_key_edit,
            self.target_column_edit, self.match_field_combo, self.write_field_combo,
            self.output_edit, self.output_button,
        ):
            widget.setEnabled(enabled)

    def _choose_pdfs(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Pilih dokumen PDF", "", "PDF (*.pdf)")
        if paths:
            self._input_paths = list(dict.fromkeys(self._input_paths + paths))
            self.input_summary.setText(f"{len(self._input_paths)} dokumen dipilih: " + ", ".join(Path(p).name for p in self._input_paths[:4]))

    def _clear_pdfs(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._input_paths.clear()
        self.input_summary.setText("Belum ada PDF dipilih")

    def _choose_source_workbook(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Pilih workbook sumber", "", "Excel Workbook (*.xlsx)")
        if path:
            self.source_workbook_edit.setText(path)
            if not self.output_edit.text().strip():
                source = Path(path)
                self.output_edit.setText(str(source.with_name(f"{source.stem}_output{source.suffix}")))

    def _choose_output_workbook(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Simpan workbook hasil", "", "Excel Workbook (*.xlsx)")
        if path:
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            self.output_edit.setText(path)

    def _build_configuration(self) -> dict[str, object]:
        base = default_configuration()
        configuration = {
            "detection": {
                "top_region_ratio": self.top_ratio_spin.value(),
                "marker_phrases": list(base["detection"]["marker_phrases"]),
                "fallback_full_page": self.fallback_check.isChecked(),
            },
            "ocr": {
                "prefer_embedded_text": self.prefer_embedded_check.isChecked(),
                "language": self.language_edit.text().strip(),
            },
            "processing": {
                "max_pages_per_document": self.max_pages_spin.value(),
                "render_dpi": self.dpi_spin.value(),
            },
            "excel": None,
        }
        if self.excel_enabled.isChecked():
            configuration["excel"] = {
                "source_workbook_path": self.source_workbook_edit.text().strip(),
                "worksheet": self.worksheet_edit.text().strip(),
                "header_row": self.header_row_spin.value(),
                "data_start_row": self.data_row_spin.value(),
                "source_key_column": self.source_key_edit.text().strip(),
                "target_column": self.target_column_edit.text().strip(),
                "match_field": self.match_field_combo.currentData(),
                "write_field": self.write_field_combo.currentData(),
                "key_type": "text",
                "normalization_profile": "remove_whitespace",
                "duplicate_policy": "review",
                "unmatched_policy": "report",
                "overwrite_policy": "empty_only",
            }
        return configuration

    def _start_job(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        if not self._input_paths:
            QMessageBox.warning(self, "Dokumen belum dipilih", "Pilih setidaknya satu dokumen PDF.")
            return
        output_path = self.output_edit.text().strip()
        if self.excel_enabled.isChecked():
            if not self.source_workbook_edit.text().strip() or not output_path:
                QMessageBox.warning(self, "Konfigurasi Excel belum lengkap", "Pilih workbook sumber dan lokasi file output.")
                return
            if self.match_field_combo.currentData() == self.write_field_combo.currentData():
                QMessageBox.warning(self, "Pemetaan tidak valid", "Field pencocokan dan field yang ditulis harus berbeda.")
                return
        if not output_path:
            output_path = str(Path(self._input_paths[0]).with_name("tax_invoice_output.xlsx"))
        try:
            configuration = self._build_configuration()
            self._feature.validate_configuration(configuration)
            request = JobRequest(
                job_id=str(uuid.uuid4()), feature_id="tax_invoice", input_paths=tuple(self._input_paths),
                output_path=output_path, configuration=configuration,
                requested_by=self._actor_id, correlation_id=str(uuid.uuid4()),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Konfigurasi tidak valid", str(getattr(exc, "safe_message", exc)))
            return

        self._clear_results()
        self.run_button.setEnabled(False)
        self.add_files_button.setEnabled(False)
        self.clear_files_button.setEnabled(False)
        self.progress.show()
        self.status_message.setText("Memproses dokumen di background…")
        self._worker = _TaxInvoiceJobWorker(self._feature, request)
        register_worker = getattr(self._feature, "register_worker", None)
        if callable(register_worker):
            register_worker(self._worker)
        self._worker.completed.connect(self._on_job_completed)
        self._worker.failed.connect(self._on_job_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _clear_results(self) -> None:
        self._last_result = None
        self.results_table.setRowCount(0)
        for card, count in (self.success_count, self.review_count, self.failed_count):
            count.setText("0")
        self.details.setText("Pilih baris hasil untuk melihat detail ekstraksi dan catatan.")

    def _on_job_completed(self, result: object) -> None:
        if not isinstance(result, JobResult):
            self._on_job_failed("The feature returned an invalid job result.")
            return
        self._last_result = result
        self.success_count[1].setText(str(result.successful_files))
        review_total = result.review_files + sum(item.status == "skipped" for item in result.results)
        self.review_count[1].setText(str(review_total))
        self.failed_count[1].setText(str(result.failed_files))
        self.results_table.setRowCount(len(result.results))
        for row, item in enumerate(result.results):
            self.results_table.setItem(row, 0, QTableWidgetItem(Path(item.source_path).name))
            self.results_table.setItem(row, 1, QTableWidgetItem(_STATUS_LABELS.get(item.status, "Need Review")))
            confidence_values = tuple(item.confidence.values())
            confidence_text = "—" if not confidence_values else f"{sum(confidence_values) / len(confidence_values):.1f}%"
            self.results_table.setItem(row, 2, QTableWidgetItem(confidence_text))
            note = "; ".join(item.warnings) or (item.error_code or "-")
            self.results_table.setItem(row, 3, QTableWidgetItem(note))
        self.status_message.setText(
            f"Selesai: {result.successful_files} Success · {review_total} Need Review · {result.failed_files} Failed"
        )
        if result.output_path:
            self.status_message.setText(self.status_message.text() + f" | Output: {result.output_path}")

    def _on_job_failed(self, message: str) -> None:
        self.status_message.setText(message)
        QMessageBox.critical(self, "Proses gagal", message)

    def _on_worker_finished(self) -> None:
        self.progress.hide()
        self.run_button.setEnabled(True)
        self.add_files_button.setEnabled(True)
        self.clear_files_button.setEnabled(True)
        worker = self._worker
        self._worker = None
        if worker is not None:
            unregister_worker = getattr(self._feature, "unregister_worker", None)
            if callable(unregister_worker):
                unregister_worker(worker)
            worker.deleteLater()

    def _show_selected_details(self) -> None:
        if self._last_result is None:
            return
        rows = self.results_table.selectionModel().selectedRows()
        if not rows:
            return
        index = rows[0].row()
        if index >= len(self._last_result.results):
            return
        item = self._last_result.results[index]
        lines = [f"Status: {_STATUS_LABELS.get(item.status, item.status)}"]
        for field_id, value in item.extracted_fields.items():
            if field_id.startswith("_"):
                continue
            if isinstance(value, Mapping):
                lines.append(f"{field_id}: {value.get('normalized_value') or value.get('raw_value') or '—'}")
        if item.error_code:
            lines.append(f"Error: {item.error_code}")
        lines.extend(f"Catatan: {warning}" for warning in item.warnings)
        self.details.setText("\n".join(lines))
