"""OCR abstraction. Confidence semantics remain engine-specific."""
from typing import Protocol
from app.services.ocr.models import ImageInput, OCROptions, OCRResult

class OCRService(Protocol):
    def recognize(self, image: ImageInput, options: OCROptions) -> OCRResult: ...
