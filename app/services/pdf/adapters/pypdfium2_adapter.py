"""PDFium implementation of the engine-neutral PDF service contract."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
from pypdfium2._helpers.misc import PdfiumError

from app.core.exceptions import ApplicationError
from app.services.models import NormalizedRegion, ResourceLimits
from app.services.pdf.models import PDFMetadata, RenderedPage


class PdfiumAdapter:
    """Read-only PDF inspection, rendering, and embedded-text adapter."""

    def __init__(self, limits: ResourceLimits | None = None) -> None:
        self._limits = limits or ResourceLimits()

    def inspect(self, path: str) -> PDFMetadata:
        source = self._validated_path(path)
        try:
            with pdfium.PdfDocument(source) as document:
                page_count = len(document)
                self._validate_page_count(page_count)
                metadata = tuple(
                    sorted(
                        (str(key), str(value))
                        for key, value in document.get_metadata_dict().items()
                        if value not in (None, "")
                    )
                )
                return PDFMetadata(
                    page_count=page_count,
                    file_size_bytes=source.stat().st_size,
                    is_encrypted=False,
                    metadata=metadata,
                )
        except ApplicationError:
            raise
        except (PdfiumError, OSError, ValueError) as exc:
            raise self._pdf_error(exc, "The PDF file is damaged or unreadable.") from exc

    def render_page(
        self,
        path: str,
        page_index: int,
        dpi: int,
        region: NormalizedRegion | None = None,
    ) -> RenderedPage:
        source = self._validated_path(path)
        if not isinstance(dpi, int) or isinstance(dpi, bool) or not 1 <= dpi <= self._limits.max_render_dpi:
            raise ApplicationError(
                "PDF_INVALID_DPI", "The requested rendering resolution is outside the allowed range."
            )
        try:
            with pdfium.PdfDocument(source) as document:
                self._validate_page_count(len(document))
                self._validate_page_index(page_index, len(document))
                page = document.get_page(page_index)
                try:
                    page_width, page_height = page.get_size()
                    scale = dpi / 72.0
                    crop = (0.0, 0.0, 0.0, 0.0)
                    width_factor, height_factor = 1.0, 1.0
                    if region is not None:
                        crop = (
                            region.x * page_width,
                            (1.0 - region.y - region.height) * page_height,
                            (1.0 - region.x - region.width) * page_width,
                            region.y * page_height,
                        )
                        width_factor, height_factor = region.width, region.height
                    estimated_width = int(page_width * width_factor * scale + 0.999)
                    estimated_height = int(page_height * height_factor * scale + 0.999)
                    if estimated_width * estimated_height > self._limits.max_image_pixels:
                        raise ApplicationError(
                            "PDF_RENDER_PIXEL_LIMIT",
                            "The requested rendering exceeds the configured pixel limit.",
                        )
                    bitmap = page.render(scale=scale, crop=crop, rev_byteorder=True)
                    try:
                        rendered = bitmap.to_pil().convert("RGB")
                        output = BytesIO()
                        rendered.save(output, format="PNG", optimize=False)
                        width, height = rendered.size
                    finally:
                        bitmap.close()
                finally:
                    page.close()
                return RenderedPage(
                    image=output.getvalue(),
                    media_type="image/png",
                    width=width,
                    height=height,
                    page_index=page_index,
                    dpi=dpi,
                )
        except ApplicationError:
            raise
        except (PdfiumError, OSError, ValueError) as exc:
            raise self._pdf_error(exc, "The PDF page could not be rendered.") from exc

    def extract_embedded_text(self, path: str, page_index: int) -> str:
        source = self._validated_path(path)
        try:
            with pdfium.PdfDocument(source) as document:
                self._validate_page_count(len(document))
                self._validate_page_index(page_index, len(document))
                page = document.get_page(page_index)
                try:
                    text_page = page.get_textpage()
                    try:
                        return text_page.get_text_range()
                    finally:
                        text_page.close()
                finally:
                    page.close()
        except ApplicationError:
            raise
        except (PdfiumError, OSError, ValueError) as exc:
            raise self._pdf_error(exc, "Text could not be extracted from the PDF page.") from exc

    def _validated_path(self, path: str) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise ApplicationError("PDF_PATH_INVALID", "A valid PDF file path is required.")
        source = Path(path).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise ApplicationError("PDF_FILE_NOT_FOUND", "The selected PDF file does not exist.")
        if source.suffix.lower() != ".pdf":
            raise ApplicationError("PDF_INVALID_FILE_TYPE", "The selected file is not a PDF.")
        size = source.stat().st_size
        if size <= 0:
            raise ApplicationError("PDF_CORRUPT", "The PDF file is empty.")
        if size > self._limits.max_file_bytes:
            raise ApplicationError("PDF_FILE_SIZE_LIMIT", "The PDF exceeds the configured file-size limit.")
        return source

    def _validate_page_count(self, page_count: int) -> None:
        if page_count <= 0:
            raise ApplicationError("PDF_CORRUPT", "The PDF does not contain any readable pages.")
        if page_count > self._limits.max_pages:
            raise ApplicationError("PDF_PAGE_LIMIT_EXCEEDED", "The PDF exceeds the configured page limit.")

    @staticmethod
    def _validate_page_index(page_index: int, page_count: int) -> None:
        if not isinstance(page_index, int) or isinstance(page_index, bool):
            raise ApplicationError("PDF_INVALID_PAGE_INDEX", "The requested PDF page index is invalid.")
        if page_index < 0 or page_index >= page_count:
            raise ApplicationError(
                "PDF_PAGE_INDEX_OUT_OF_RANGE", "The requested PDF page does not exist.",
                details={"page_index": page_index, "page_count": page_count},
            )

    @staticmethod
    def _pdf_error(error: Exception, fallback: str) -> ApplicationError:
        if isinstance(error, PdfiumError) and error.err_code == pdfium_raw.FPDF_ERR_PASSWORD:
            return ApplicationError("PDF_ENCRYPTED", "The PDF is password-protected and cannot be processed.")
        return ApplicationError("PDF_CORRUPT", fallback)
