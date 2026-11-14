"""PDF service request and response models."""
from dataclasses import dataclass
from typing import Literal

from app.services.models import NormalizedRegion

@dataclass(frozen=True, slots=True)
class PDFMetadata:
    page_count: int
    file_size_bytes: int
    is_encrypted: bool
    metadata: tuple[tuple[str, str], ...] = ()

@dataclass(frozen=True, slots=True)
class RenderedPage:
    image: bytes
    media_type: Literal["image/png", "image/jpeg", "image/tiff"]
    width: int
    height: int
    page_index: int
    dpi: int

@dataclass(frozen=True, slots=True)
class PDFTextPage:
    page_index: int
    text: str
