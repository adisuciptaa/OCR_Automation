from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from app.core.exceptions import ApplicationError
from app.services.image.adapters import OpenCVImageAdapter
from app.services.models import NormalizedRegion, ResourceLimits
from app.services.ocr.models import ImageInput


def make_image(width: int = 100, height: int = 80) -> ImageInput:
    array = np.full((height, width, 3), 255, dtype=np.uint8)
    array[20:60, 20:80] = (20, 20, 20)
    output = BytesIO()
    Image.fromarray(array).save(output, format="PNG")
    return ImageInput(output.getvalue(), "image/png")


def dimensions(image: ImageInput) -> tuple[int, int]:
    with Image.open(BytesIO(image.data)) as decoded:
        return decoded.size


def test_crop_uses_normalized_coordinates() -> None:
    result = OpenCVImageAdapter().crop(make_image(), NormalizedRegion(0.0, 0.0, 0.5, 0.5))
    assert dimensions(result) == (50, 40)
    assert result.media_type == "image/png"


@pytest.mark.parametrize("operation", ["deskew", "denoise", "enhance_contrast"])
def test_image_transformations_return_new_png(operation: str) -> None:
    adapter = OpenCVImageAdapter()
    source = make_image()
    original = source.data
    if operation == "deskew":
        result = adapter.deskew(source)
    elif operation == "denoise":
        result = adapter.denoise(source, "standard")
    else:
        result = adapter.enhance_contrast(source, "standard")
    assert result.media_type == "image/png"
    assert result.data
    assert source.data == original
    assert dimensions(result) == (100, 80)


def test_rejects_unsupported_profile() -> None:
    with pytest.raises(ApplicationError) as error:
        OpenCVImageAdapter().denoise(make_image(), "unknown")
    assert error.value.code == "IMAGE_PROFILE_INVALID"


def test_rejects_invalid_image_bytes() -> None:
    with pytest.raises(ApplicationError) as error:
        OpenCVImageAdapter().deskew(ImageInput(b"not an image", "image/png"))
    assert error.value.code == "IMAGE_DECODE_FAILED"


def test_enforces_pixel_limit() -> None:
    with pytest.raises(ApplicationError) as error:
        OpenCVImageAdapter(ResourceLimits(max_image_pixels=10)).deskew(make_image())
    assert error.value.code == "IMAGE_PIXEL_LIMIT_EXCEEDED"


def test_rejects_empty_input() -> None:
    with pytest.raises(ApplicationError) as error:
        OpenCVImageAdapter().deskew(ImageInput(b"", "image/png"))
    assert error.value.code == "IMAGE_INPUT_INVALID"


def test_rejects_mismatched_declared_media_type() -> None:
    source = make_image()
    with pytest.raises(ApplicationError) as error:
        OpenCVImageAdapter().deskew(ImageInput(source.data, "image/jpeg"))
    assert error.value.code == "IMAGE_MEDIA_TYPE_MISMATCH"
