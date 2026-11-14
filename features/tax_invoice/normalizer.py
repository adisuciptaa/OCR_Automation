"""Conservative normalization for Tax Invoice identifiers."""
from __future__ import annotations

import re
import unicodedata

_TAX_INVOICE_ALLOWED = re.compile(r"^[0-9.\-\s]+$")
_TAX_INVOICE_COMPACT = re.compile(r"^[0-9]{16}$")


def normalize_tax_invoice_number(raw_value: str) -> str | None:
    """Return canonical 000.000-00.00000000 form, or None when ambiguous/invalid.

    Only ASCII digits and the documented separators (dot, hyphen, whitespace)
    are accepted. No OCR character substitution or digit guessing is performed.
    """
    value = unicodedata.normalize("NFKC", raw_value).strip()
    if not value or not _TAX_INVOICE_ALLOWED.fullmatch(value):
        return None
    compact = re.sub(r"[.\-\s]", "", value)
    if not _TAX_INVOICE_COMPACT.fullmatch(compact):
        return None
    return f"{compact[:3]}.{compact[3:6]}-{compact[6:8]}.{compact[8:]}"


def normalize_invoice_number(raw_value: str) -> str | None:
    """Remove all whitespace; preserve case and meaningful punctuation.

    Raw OCR text is retained separately on TaxInvoiceFieldValue.
    """
    value = unicodedata.normalize("NFKC", raw_value)
    value = "".join(value.split())
    if not value or len(value) > 100:
        return None
    if any(unicodedata.category(char) == "Cc" for char in value):
        return None
    if not any(char.isalnum() for char in value):
        return None
    return value
