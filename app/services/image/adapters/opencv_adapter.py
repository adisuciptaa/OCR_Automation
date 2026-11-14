"""Pillow/OpenCV implementation of the engine-neutral image service contract."""
from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.exceptions import ApplicationError
from app.services.models import NormalizedRegion, ResourceLimits
from app.services.ocr.models import ImageInput


class OpenCVImageAdapter:
    """Deterministic image transformations that never mutate the input bytes."""

    _DENOISE_PROFILES = {
        "light": (7, 5, 5),
        "standard": (10, 7, 7),
        "strong": (15, 10, 10),
    }
    _CONTRAST_PROFILES = {"light": (2.0, 8), "standard": (2.5, 8), "strong": (3.0, 8)}

    def __init__(self, limits: ResourceLimits | None = None) -> None:
        self._limits = limits or ResourceLimits()

    def crop(self, image: ImageInput, region: NormalizedRegion) -> ImageInput:
        source = self._decode(image)
        width, height = source.size
        left = int(round(region.x * width))
        top = int(round(region.y * height))
        right = int(round((region.x + region.width) * width))
        bottom = int(round((region.y + region.height) * height))
        cropped = source.crop((left, top, max(left + 1, right), max(top + 1, bottom)))
        return self._encode(cropped)

    def deskew(self, image: ImageInput) -> ImageInput:
        source = self._decode(image).convert("RGB")
        array = np.asarray(source)
        gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        points = cv2.findNonZero(binary)
        if points is None or len(points) < 10:
            return self._encode(source)
        angle = cv2.minAreaRect(points)[-1]
        angle = -(90.0 + angle) if angle < -45.0 else -angle
        if abs(angle) < 0.15 or abs(angle) > 15.0:
            return self._encode(source)
        height, width = gray.shape
        matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
        rotated = cv2.warpAffine(
            array, matrix, (width, height), flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255),
        )
        return self._encode(Image.fromarray(rotated))

    def denoise(self, image: ImageInput, profile: str) -> ImageInput:
        parameters = self._DENOISE_PROFILES.get(profile)
        if parameters is None:
            raise ApplicationError("IMAGE_PROFILE_INVALID", "The selected denoising profile is not supported.")
        source = self._decode(image).convert("RGB")
        array = np.asarray(source)
        diameter, sigma_color, sigma_space = parameters
        result = cv2.bilateralFilter(array, diameter, sigma_color, sigma_space)
        return self._encode(Image.fromarray(result))

    def enhance_contrast(self, image: ImageInput, profile: str) -> ImageInput:
        parameters = self._CONTRAST_PROFILES.get(profile)
        if parameters is None:
            raise ApplicationError("IMAGE_PROFILE_INVALID", "The selected contrast profile is not supported.")
        source = self._decode(image).convert("RGB")
        array = cv2.cvtColor(np.asarray(source), cv2.COLOR_RGB2LAB)
        lightness, channel_a, channel_b = cv2.split(array)
        clip_limit, tile_size = parameters
        enhanced = cv2.createCLAHE(
            clipLimit=clip_limit, tileGridSize=(tile_size, tile_size)
        ).apply(lightness)
        result = cv2.cvtColor(cv2.merge((enhanced, channel_a, channel_b)), cv2.COLOR_LAB2RGB)
        return self._encode(Image.fromarray(result))

    def _decode(self, image: ImageInput) -> Image.Image:
        if not isinstance(image, ImageInput) or not isinstance(image.data, bytes) or not image.data:
            raise ApplicationError("IMAGE_INPUT_INVALID", "A non-empty encoded image is required.")
        try:
            with Image.open(BytesIO(image.data)) as opened:
                supported_formats = {"PNG", "JPEG", "TIFF", "BMP", "WEBP"}
                if opened.format not in supported_formats:
                    raise ApplicationError("IMAGE_FORMAT_UNSUPPORTED", "The image format is not supported.")
                declared_types = {
                    "PNG": "image/png", "JPEG": "image/jpeg", "TIFF": "image/tiff",
                    "BMP": "image/bmp", "WEBP": "image/webp",
                }
                if image.media_type != declared_types[opened.format]:
                    raise ApplicationError("IMAGE_MEDIA_TYPE_MISMATCH", "The image media type does not match its content.")
                width, height = opened.size
                if width <= 0 or height <= 0 or width * height > self._limits.max_image_pixels:
                    raise ApplicationError("IMAGE_PIXEL_LIMIT_EXCEEDED", "The image exceeds the configured pixel limit.")
                if len(image.data) > self._limits.max_file_bytes:
                    raise ApplicationError("IMAGE_FILE_SIZE_LIMIT", "The image exceeds the configured file-size limit.")
                opened.load()
                return ImageOps.exif_transpose(opened).copy()
        except ApplicationError:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ApplicationError("IMAGE_DECODE_FAILED", "The image is damaged or cannot be decoded.") from exc

    @staticmethod
    def _encode(image: Image.Image) -> ImageInput:
        output = BytesIO()
        image.save(output, format="PNG", optimize=False)
        return ImageInput(data=output.getvalue(), media_type="image/png")
