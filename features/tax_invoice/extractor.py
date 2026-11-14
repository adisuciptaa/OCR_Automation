"""Tax Invoice document detection and raw identifier extraction pipeline."""
from __future__ import annotations

import re
from dataclasses import replace
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.core.exceptions import ApplicationError
from app.services.models import NormalizedRegion
from app.services.ocr.interfaces import OCRService
from app.services.ocr.models import ImageInput, OCRResult, OCROptions
from app.services.pdf.interfaces import PDFService
from features.tax_invoice.detector import build_detection
from features.tax_invoice.models import (
    TaxInvoiceExtraction,
    TaxInvoiceFieldValue,
    TaxInvoicePageDetection,
)
from features.tax_invoice.validator import TaxInvoiceValidator

_FULL_REGION = NormalizedRegion(0.0, 0.0, 1.0, 1.0)
_TAX_NUMBER_PATTERNS = (
    re.compile(r"(?:KODE\s*(?:DAN|&)\s*)?NOMOR\s*(?:SERI\s*)?FAKTUR\s*PAJAK\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./\-]{5,})", re.I),
    re.compile(r"FAKTUR\s*PAJAK\s*(?:NO\.?|NOMOR)?\s*[:#\-]\s*([A-Z0-9][A-Z0-9./\-]{5,})", re.I),
)
_INVOICE_NUMBER_PATTERNS = (
    re.compile(r"(?:NO\.?\s*)?INVOICE\s*(?:NO\.?|NOMOR)?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./\-_]{2,})", re.I),
    re.compile(r"NOMOR\s*INVOICE\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./\-_]{2,})", re.I),
)


class TaxInvoiceExtractor:
    """Coordinates existing PDF/OCR services for one tax-invoice feature."""

    def __init__(self, pdf: PDFService, ocr: OCRService, configuration: Mapping[str, Any]) -> None:
        self._pdf = pdf
        self._ocr = ocr
        self._config = configuration
        detection = configuration["detection"]
        ocr_config = configuration["ocr"]
        processing = configuration["processing"]
        self._markers = tuple(str(item) for item in detection["marker_phrases"])
        self._top_ratio = float(detection["top_region_ratio"])
        self._fallback = bool(detection["fallback_full_page"])
        self._prefer_embedded = bool(ocr_config["prefer_embedded_text"])
        self._languages = tuple(part.strip() for part in str(ocr_config["language"]).split("+") if part.strip())
        self._max_pages = int(processing["max_pages_per_document"])
        self._dpi = int(processing.get("render_dpi", 200))
        if not self._languages:
            raise ApplicationError("TAX_INVOICE_OCR_LANGUAGE_INVALID", "At least one OCR language is required.")

    def process(self, source_path: str) -> TaxInvoiceExtraction:
        """Detect candidate pages and extract raw identifiers from a PDF."""
        path = str(Path(source_path).expanduser())
        metadata = self._pdf.inspect(path)
        if metadata.is_encrypted:
            raise ApplicationError("TAX_INVOICE_PDF_ENCRYPTED", "The PDF is encrypted and cannot be processed.")
        if metadata.page_count > self._max_pages:
            raise ApplicationError(
                "TAX_INVOICE_PAGE_LIMIT", "The document exceeds the configured page limit.",
                details={"page_count": metadata.page_count, "maximum": self._max_pages},
            )

        detections: list[TaxInvoicePageDetection] = []
        warnings: list[str] = []
        extracted_text: dict[int, tuple[str, OCRResult | None]] = {}

        for page_index in range(metadata.page_count):
            embedded = ""
            if self._prefer_embedded:
                embedded = self._pdf.extract_embedded_text(path, page_index).strip()
            top_ratio_region = NormalizedRegion(0.0, 0.0, 1.0, self._top_ratio)
            if embedded:
                embedded_detection = build_detection(
                    page_index=page_index,
                    text=embedded,
                    marker_phrases=self._markers,
                    search_region=top_ratio_region,
                    source="embedded_text_page",
                )
                if embedded_detection.is_candidate:
                    detections.append(embedded_detection)
                    extracted_text[page_index] = (embedded, None)
                    continue

            top_ocr = self._recognize(path, page_index, top_ratio_region)
            detection = build_detection(
                page_index=page_index,
                text=top_ocr.text,
                marker_phrases=self._markers,
                search_region=top_ratio_region,
                source="ocr_top_region",
            )
            if not detection.is_candidate and self._fallback:
                full_ocr = self._recognize(path, page_index, _FULL_REGION)
                detection = build_detection(
                    page_index=page_index,
                    text=full_ocr.text,
                    marker_phrases=self._markers,
                    search_region=_FULL_REGION,
                    source="ocr_full_page",
                    fallback_used=True,
                )
                if detection.is_candidate:
                    extracted_text[page_index] = (full_ocr.text, full_ocr)
                if full_ocr.warnings:
                    warnings.extend(full_ocr.warnings)
            elif detection.is_candidate:
                # The top-region OCR is retained for detection only; extraction below uses the full page.
                full_ocr = self._recognize(path, page_index, _FULL_REGION)
                extracted_text[page_index] = (full_ocr.text, full_ocr)
                if full_ocr.warnings:
                    warnings.extend(full_ocr.warnings)
            detections.append(detection)
            if top_ocr.warnings:
                warnings.extend(top_ocr.warnings)

        if not any(item.is_candidate for item in detections):
            return TaxInvoiceExtraction(
                source_path=path, status="review", page_count=metadata.page_count,
                detections=tuple(detections), tax_invoice_number=None, invoice_number=None,
                warnings=tuple(dict.fromkeys(warnings + ["TAX_INVOICE_MARKER_NOT_FOUND"])),
            )

        tax_occurrences = self._extract_field_candidates(extracted_text, _TAX_NUMBER_PATTERNS)
        invoice_occurrences = self._extract_field_candidates(extracted_text, _INVOICE_NUMBER_PATTERNS)
        tax_value = tax_occurrences[0] if tax_occurrences else None
        invoice_value = invoice_occurrences[0] if invoice_occurrences else None
        validation = TaxInvoiceValidator().validate(
            tax_value,
            invoice_value,
            {
                "tax_invoice_number": tuple(item.raw_value or "" for item in tax_occurrences),
                "invoice_number": tuple(item.raw_value or "" for item in invoice_occurrences),
            },
        )
        normalized_by_id = {item.field_id: item.normalized_value for item in validation.fields}
        if tax_value is not None:
            tax_value = replace(tax_value, normalized_value=normalized_by_id.get("tax_invoice_number"))
        if invoice_value is not None:
            invoice_value = replace(invoice_value, normalized_value=normalized_by_id.get("invoice_number"))
        warnings.extend(validation.warnings)
        status = "success" if validation.status == "valid" else "review"
        return TaxInvoiceExtraction(
            source_path=path,
            status=status,
            page_count=metadata.page_count,
            detections=tuple(detections),
            tax_invoice_number=tax_value,
            invoice_number=invoice_value,
            warnings=tuple(dict.fromkeys(warnings)),
            validation=validation,
        )

    def _recognize(self, path: str, page_index: int, region: NormalizedRegion) -> OCRResult:
        rendered = self._pdf.render_page(path, page_index, self._dpi, region)
        return self._ocr.recognize(
            ImageInput(rendered.image, rendered.media_type),
            OCROptions(languages=self._languages, page_segmentation_mode="6"),
        )

    @staticmethod
    def _extract_field_candidates(
        page_text: Mapping[int, tuple[str, OCRResult | None]],
        patterns: tuple[re.Pattern[str], ...],
    ) -> tuple[TaxInvoiceFieldValue, ...]:
        """Collect candidate values in page order for conflict detection."""
        candidates: list[TaxInvoiceFieldValue] = []
        field_id = "tax_invoice_number" if patterns is _TAX_NUMBER_PATTERNS else "invoice_number"
        for page_index in sorted(page_text):
            text, ocr_result = page_text[page_index]
            for pattern in patterns:
                for match in pattern.finditer(text):
                    raw = match.group(1).strip().rstrip(".,;:")
                    if not raw:
                        continue
                    confidence = ocr_result.confidence if ocr_result else None
                    confidence_kind = "engine_score" if confidence is not None else "unavailable"
                    candidates.append(TaxInvoiceFieldValue(
                        field_id=field_id,
                        raw_value=raw,
                        normalized_value=None,
                        page_index=page_index,
                        confidence=confidence,
                        confidence_kind=confidence_kind,
                    ))
        return tuple(candidates)
