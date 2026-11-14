"""Tax Invoice feature configuration identifiers and immutable defaults."""
from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import Any, Mapping

CONFIGURATION_SCHEMA_VERSION = 1

_DEFAULTS: dict[str, Any] = {
    "detection": {
        "top_region_ratio": 0.25,
        "marker_phrases": ["FAKTUR PAJAK", "FAKTURPAJAK"],
        "fallback_full_page": False,
    },
    "ocr": {
        "prefer_embedded_text": True,
        "language": "ind+eng",
    },
    "processing": {
        "max_pages_per_document": 200,
        "render_dpi": 200,
    },
}


def default_configuration() -> Mapping[str, object]:
    """Return a fresh, caller-owned copy of the feature's default configuration."""
    return MappingProxyType(deepcopy(_DEFAULTS))
