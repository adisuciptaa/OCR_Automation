"""Tax Invoice page-candidate detection using embedded text or OCR text."""
from __future__ import annotations

import re
from collections.abc import Iterable

from app.services.models import NormalizedRegion
from features.tax_invoice.models import TaxInvoicePageDetection


def _canonical_text(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def find_markers(text: str, marker_phrases: Iterable[str]) -> tuple[str, ...]:
    """Return configured markers found in text, ignoring punctuation and spacing."""
    canonical = _canonical_text(text)
    matches: list[str] = []
    for phrase in marker_phrases:
        if _canonical_text(phrase) and _canonical_text(phrase) in canonical:
            matches.append(phrase)
    return tuple(matches)


def build_detection(
    *,
    page_index: int,
    text: str,
    marker_phrases: Iterable[str],
    search_region: NormalizedRegion,
    source: str,
    fallback_used: bool = False,
) -> TaxInvoicePageDetection:
    """Build a stable detection result without retaining potentially sensitive OCR text."""
    markers = find_markers(text, marker_phrases)
    reasons = (f"marker_found_{source}",) if markers else (f"marker_not_found_{source}",)
    if fallback_used:
        reasons += ("full_page_fallback_used",)
    return TaxInvoicePageDetection(
        page_index=page_index,
        is_candidate=bool(markers),
        search_region=search_region,
        matched_markers=markers,
        reason_codes=reasons,
        fallback_used=fallback_used,
    )
