"""Reporting service interface."""
from typing import Protocol
from app.services.reporting.models import ProcessingReport

class ReportService(Protocol):
    def build_report(self, report: ProcessingReport) -> bytes: ...
    def write_report(self, report: ProcessingReport, destination_path: str) -> str: ...
