"""Tesseract implementation of the engine-neutral OCR service contract."""
from __future__ import annotations

import math
import re
from collections import OrderedDict
from io import BytesIO
from statistics import mean

import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError
from pytesseract import Output
from pytesseract.pytesseract import TesseractError, TesseractNotFoundError

from app.core.exceptions import ApplicationError
from app.services.models import ResourceLimits
from app.services.ocr.models import (
    BoundingBox,
    ImageInput,
    OCRLine,
    OCROptions,
    OCRResult,
    OCRWord,
)


class TesseractOCRAdapter:
    """Run local Tesseract OCR and translate its output into public OCR models.

    The adapter owns no global engine process. Tesseract is invoked per request by
    pytesseract, and all vendor-specific objects are converted before returning.
    """

    _MEDIA_TYPES = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "TIFF": "image/tiff",
        "BMP": "image/bmp",
        "WEBP": "image/webp",
    }
    _LANGUAGE_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")

    def __init__(
        self,
        limits: ResourceLimits | None = None,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a finite positive number")
        self._limits = limits or ResourceLimits()
        self._timeout_seconds = timeout_seconds

    def recognize(self, image: ImageInput, options: OCROptions) -> OCRResult:
        decoded = self._decode(image)
        self._validate_options(options)
        languages = "+".join(options.languages)
        config_parts: list[str] = []
        if options.page_segmentation_mode is not None:
            config_parts.extend(("--psm", options.page_segmentation_mode))
        if options.preserve_interword_spaces:
            config_parts.extend(("-c", "preserve_interword_spaces=1"))
        config = " ".join(config_parts)

        try:
            available_languages = set(pytesseract.get_languages(config=""))
            missing_languages = tuple(
                language for language in options.languages if language not in available_languages
            )
            if missing_languages:
                raise ApplicationError(
                    "OCR_LANGUAGE_UNAVAILABLE",
                    "One or more requested OCR language packs are not installed.",
                    details={"languages": missing_languages},
                )
            raw_data = pytesseract.image_to_data(
                decoded,
                lang=languages,
                config=config,
                output_type=Output.DICT,
                timeout=self._timeout_seconds,
            )
            engine_version = str(pytesseract.get_tesseract_version()).strip()
        except ApplicationError:
            raise
        except TesseractNotFoundError as exc:
            raise ApplicationError(
                "OCR_ENGINE_UNAVAILABLE", "The local Tesseract OCR engine is not installed or not configured."
            ) from exc
        except RuntimeError as exc:
            # pytesseract uses RuntimeError for a terminated process, including timeout.
            raise ApplicationError(
                "OCR_EXECUTION_FAILED", "OCR processing failed or exceeded its time limit."
            ) from exc
        except (TesseractError, OSError) as exc:
            raise ApplicationError(
                "OCR_EXECUTION_FAILED", "The local OCR engine could not process this image."
            ) from exc

        lines, confidences = self._parse_data(raw_data)
        overall_confidence = mean(confidences) if confidences else None
        return OCRResult(
            text="\n".join(line.text for line in lines),
            lines=lines,
            engine_id="tesseract",
            engine_version=engine_version,
            languages=options.languages,
            confidence=overall_confidence,
            confidence_kind="engine_score" if overall_confidence is not None else "unavailable",
        )

    def _decode(self, image: ImageInput) -> Image.Image:
        if not isinstance(image, ImageInput) or not isinstance(image.data, bytes) or not image.data:
            raise ApplicationError("OCR_INPUT_INVALID", "A non-empty encoded image is required for OCR.")
        if len(image.data) > self._limits.max_file_bytes:
            raise ApplicationError(
                "OCR_FILE_SIZE_LIMIT", "The image exceeds the configured OCR input-size limit."
            )
        try:
            with Image.open(BytesIO(image.data)) as opened:
                expected_media_type = self._MEDIA_TYPES.get(opened.format or "")
                if expected_media_type is None:
                    raise ApplicationError(
                        "OCR_IMAGE_FORMAT_UNSUPPORTED", "The image format is not supported by the OCR adapter."
                    )
                if image.media_type != expected_media_type:
                    raise ApplicationError(
                        "OCR_MEDIA_TYPE_MISMATCH", "The declared image media type does not match its content."
                    )
                width, height = opened.size
                if width <= 0 or height <= 0 or width * height > self._limits.max_image_pixels:
                    raise ApplicationError(
                        "OCR_IMAGE_PIXEL_LIMIT", "The image exceeds the configured OCR pixel limit."
                    )
                opened.load()
                return ImageOps.exif_transpose(opened).copy()
        except ApplicationError:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ApplicationError(
                "OCR_IMAGE_DECODE_FAILED", "The image is damaged or cannot be decoded for OCR."
            ) from exc

    @classmethod
    def _validate_options(cls, options: OCROptions) -> None:
        if not isinstance(options, OCROptions):
            raise ApplicationError("OCR_OPTIONS_INVALID", "Valid OCR options are required.")
        if (
            not isinstance(options.languages, tuple)
            or not options.languages
            or any(
                not isinstance(language, str)
                or not cls._LANGUAGE_PATTERN.fullmatch(language)
                for language in options.languages
            )
            or len(set(options.languages)) != len(options.languages)
        ):
            raise ApplicationError("OCR_OPTIONS_INVALID", "The requested OCR languages are invalid.")
        mode = options.page_segmentation_mode
        if mode is not None and (not isinstance(mode, str) or not mode.isdigit() or not 0 <= int(mode) <= 13):
            raise ApplicationError("OCR_OPTIONS_INVALID", "The OCR page segmentation mode must be between 0 and 13.")
        if not isinstance(options.preserve_interword_spaces, bool):
            raise ApplicationError("OCR_OPTIONS_INVALID", "The interword spacing option must be a boolean.")

    @staticmethod
    def _parse_data(data: dict[str, list[object]]) -> tuple[tuple[OCRLine, ...], list[float]]:
        grouped: OrderedDict[tuple[int, int, int], list[OCRWord]] = OrderedDict()
        line_text: dict[tuple[int, int, int], list[str]] = {}
        confidences: list[float] = []
        count = len(data.get("text", []))
        for index in range(count):
            text = str(data["text"][index]).strip()
            try:
                confidence = float(data["conf"][index])
                left = int(data["left"][index])
                top = int(data["top"][index])
                width = int(data["width"][index])
                height = int(data["height"][index])
                key = (
                    int(data["block_num"][index]),
                    int(data["par_num"][index]),
                    int(data["line_num"][index]),
                )
            except (KeyError, TypeError, ValueError, IndexError):
                continue
            if not text or confidence < 0:
                continue
            box = BoundingBox(x=left, y=top, width=width, height=height)
            grouped.setdefault(key, []).append(
                OCRWord(text=text, bounds=box, confidence=confidence)
            )
            line_text.setdefault(key, []).append(text)
            confidences.append(confidence)

        lines = tuple(
            OCRLine(text=" ".join(line_text[key]), words=tuple(words))
            for key, words in grouped.items()
        )
        return lines, confidences
