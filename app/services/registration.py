"""Typed registration helper for Shared Services at the composition root."""
from dataclasses import dataclass

from app.core.service_registry import ServiceRegistry
from app.services.excel.adapters import OpenpyxlExcelAdapter
from app.services.excel.interfaces import ExcelService
from app.services.image.adapters import OpenCVImageAdapter
from app.services.image.interfaces import ImageService
from app.services.ocr.adapters import TesseractOCRAdapter
from app.services.ocr.interfaces import OCRService
from app.services.pdf.adapters import PdfiumAdapter
from app.services.pdf.interfaces import PDFService
from app.services.reporting.interfaces import ReportService
from app.services.validation.interfaces import ValidationService

@dataclass(frozen=True, slots=True)
class SharedServiceImplementations:
    pdf: PDFService
    ocr: OCRService
    image: ImageService
    excel: ExcelService
    validation: ValidationService
    reporting: ReportService

def register_shared_services(
    registry: ServiceRegistry, services: SharedServiceImplementations
) -> None:
    """Register one implementation for each stable public service ID."""
    registrations = (
        ("pdf.render", services.pdf),
        ("ocr.recognize", services.ocr),
        ("image.process", services.image),
        ("excel.workbook", services.excel),
        ("validation.generic", services.validation),
        ("reporting.generate", services.reporting),
    )
    for service_id, implementation in registrations:
        registry.register(service_id, implementation, version="1.0.0")


def register_document_processing_services(registry: ServiceRegistry) -> None:
    """Register concrete document-processing adapters at the composition root."""
    registry.register("pdf.render", PdfiumAdapter(), version="1.0.0")
    registry.register("ocr.recognize", TesseractOCRAdapter(), version="1.0.0")
    registry.register("image.process", OpenCVImageAdapter(), version="1.0.0")
    registry.register("excel.workbook", OpenpyxlExcelAdapter(), version="1.0.0")
