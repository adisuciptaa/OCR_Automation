"""Public Excel service contracts and engine-neutral models."""

from app.services.excel.interfaces import ExcelService
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

__all__ = [
    "ExcelService",
    "ExcelMapping",
    "ExcelReadRequest",
    "ExcelReadResult",
    "ExcelRecord",
    "ExcelWriteRequest",
    "ExcelWriteResult",
    "WorkbookDescriptor",
    "WorkbookVerificationResult",
]
