from __future__ import annotations

from app.core.service_registry import ServiceRegistry
from app.services.registration import SharedServiceImplementations, register_shared_services


class FakePDF: pass
class FakeOCR: pass
class FakeImage: pass
class FakeExcel: pass
class FakeValidation: pass
class FakeReporting: pass


def test_register_shared_services_exposes_stable_ids_through_provider() -> None:
    registry = ServiceRegistry()
    implementations = SharedServiceImplementations(
        pdf=FakePDF(), ocr=FakeOCR(), image=FakeImage(), excel=FakeExcel(),
        validation=FakeValidation(), reporting=FakeReporting(),
    )
    register_shared_services(registry, implementations)
    expected = {
        "pdf.render": implementations.pdf,
        "ocr.recognize": implementations.ocr,
        "image.process": implementations.image,
        "excel.workbook": implementations.excel,
        "validation.generic": implementations.validation,
        "reporting.generate": implementations.reporting,
    }
    for service_id, instance in expected.items():
        assert registry.provider.get(service_id, "1.x") is instance
    assert not hasattr(registry.provider, "register")


def test_register_document_processing_services_registers_stage12_adapters() -> None:
    from app.services.registration import register_document_processing_services
    from app.services.excel.adapters import OpenpyxlExcelAdapter
    from app.services.image.adapters import OpenCVImageAdapter
    from app.services.ocr.adapters import TesseractOCRAdapter
    from app.services.pdf.adapters import PdfiumAdapter

    registry = ServiceRegistry()
    register_document_processing_services(registry)

    assert isinstance(registry.provider.get("pdf.render", "1.x"), PdfiumAdapter)
    assert isinstance(registry.provider.get("ocr.recognize", "1.x"), TesseractOCRAdapter)
    assert isinstance(registry.provider.get("image.process", "1.x"), OpenCVImageAdapter)
    assert isinstance(registry.provider.get("excel.workbook", "1.x"), OpenpyxlExcelAdapter)
