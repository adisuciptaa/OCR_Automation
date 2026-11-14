"""Engine-neutral OCR request and result models."""
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True, slots=True)
class ImageInput:
    data: bytes
    media_type: str

@dataclass(frozen=True, slots=True)
class OCROptions:
    languages: tuple[str, ...] = ("eng",)
    page_segmentation_mode: str | None = None
    preserve_interword_spaces: bool = True

@dataclass(frozen=True, slots=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

@dataclass(frozen=True, slots=True)
class OCRWord:
    text: str
    bounds: BoundingBox | None = None
    confidence: float | None = None

@dataclass(frozen=True, slots=True)
class OCRLine:
    text: str
    words: tuple[OCRWord, ...] = ()

@dataclass(frozen=True, slots=True)
class OCRResult:
    text: str
    lines: tuple[OCRLine, ...]
    engine_id: str
    engine_version: str
    languages: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    preprocessing: tuple[str, ...] = ()
    confidence: float | None = None
    confidence_kind: Literal["engine_score", "unavailable"] = "unavailable"
