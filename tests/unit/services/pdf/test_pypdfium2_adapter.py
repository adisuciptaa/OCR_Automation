from __future__ import annotations

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
import pytest

from app.core.exceptions import ApplicationError
from app.services.models import NormalizedRegion, ResourceLimits
from app.services.pdf.adapters import PdfiumAdapter


@pytest.fixture
def sample_pdf(tmp_path):
    path = tmp_path / "sample.pdf"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = b"BT /F1 12 Tf 30 350 Td (OCR Automation Stage 10) Tj ET"
    objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    pdf_bytes = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(pdf_bytes))
        pdf_bytes.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(pdf_bytes)
    pdf_bytes.extend(f"xref\n0 {len(offsets)}\n".encode())
    pdf_bytes.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf_bytes.extend(f"{offset:010d} 00000 n \n".encode())
    pdf_bytes.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    )
    path.write_bytes(pdf_bytes)
    return path


def test_inspect_pdf_metadata(sample_pdf) -> None:
    metadata = PdfiumAdapter().inspect(str(sample_pdf))
    assert metadata.page_count == 1
    assert metadata.file_size_bytes == sample_pdf.stat().st_size
    assert metadata.is_encrypted is False


def test_render_page_returns_png_and_dimensions(sample_pdf) -> None:
    rendered = PdfiumAdapter().render_page(str(sample_pdf), 0, 72)
    assert rendered.media_type == "image/png"
    assert rendered.width == 300
    assert rendered.height == 400
    assert rendered.page_index == 0
    assert rendered.image.startswith(b"\x89PNG")


def test_render_page_supports_normalized_region(sample_pdf) -> None:
    rendered = PdfiumAdapter().render_page(
        str(sample_pdf), 0, 72, NormalizedRegion(0.0, 0.0, 0.5, 0.5)
    )
    assert rendered.width == 150
    assert rendered.height == 200


def test_extract_embedded_text(sample_pdf) -> None:
    text = PdfiumAdapter().extract_embedded_text(str(sample_pdf), 0)
    assert "OCR Automation Stage 10" in text


def test_rejects_invalid_page_index(sample_pdf) -> None:
    with pytest.raises(ApplicationError) as error:
        PdfiumAdapter().render_page(str(sample_pdf), 1, 72)
    assert error.value.code == "PDF_PAGE_INDEX_OUT_OF_RANGE"


def test_rejects_non_pdf_file(tmp_path) -> None:
    path = tmp_path / "not_pdf.txt"
    path.write_text("not a pdf")
    with pytest.raises(ApplicationError) as error:
        PdfiumAdapter().inspect(str(path))
    assert error.value.code == "PDF_INVALID_FILE_TYPE"


def test_enforces_file_size_limit(sample_pdf) -> None:
    adapter = PdfiumAdapter(ResourceLimits(max_file_bytes=1))
    with pytest.raises(ApplicationError) as error:
        adapter.inspect(str(sample_pdf))
    assert error.value.code == "PDF_FILE_SIZE_LIMIT"


def test_maps_pdfium_password_error_to_encrypted_code(monkeypatch, tmp_path) -> None:
    def raise_password_error(*args, **kwargs):
        error = pdfium.PdfiumError("password required")
        error.err_code = pdfium_raw.FPDF_ERR_PASSWORD
        raise error

    path = tmp_path / "valid.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(pdfium, "PdfDocument", raise_password_error)
    with pytest.raises(ApplicationError) as error:
        PdfiumAdapter().inspect(str(path))
    assert error.value.code == "PDF_ENCRYPTED"


def test_preflights_render_pixel_limit_before_rendering(sample_pdf) -> None:
    adapter = PdfiumAdapter(ResourceLimits(max_image_pixels=100))
    with pytest.raises(ApplicationError) as error:
        adapter.render_page(str(sample_pdf), 0, 72)
    assert error.value.code == "PDF_RENDER_PIXEL_LIMIT"
