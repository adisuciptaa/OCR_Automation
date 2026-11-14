from __future__ import annotations

from io import BytesIO
import pytest
from PIL import Image

from app.core.exceptions import ApplicationError
from app.services.models import ResourceLimits
from app.services.ocr.adapters import TesseractOCRAdapter
from app.services.ocr.models import ImageInput, OCROptions


def make_image(width: int = 80, height: int = 40) -> ImageInput:
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return ImageInput(output.getvalue(), "image/png")


def fake_data() -> dict[str, list[object]]:
    return {
        "level": [5, 5, 5],
        "page_num": [1, 1, 1],
        "block_num": [1, 1, 1],
        "par_num": [1, 1, 1],
        "line_num": [1, 1, 1],
        "word_num": [1, 2, 3],
        "left": [10, 35, 55],
        "top": [8, 8, 8],
        "width": [20, 15, 18],
        "height": [12, 12, 12],
        "conf": [90.0, 80.0, -1.0],
        "text": ["Invoice", "No", ""],
    }


def patch_engine(monkeypatch, *, data=None) -> None:
    import app.services.ocr.adapters.tesseract_adapter as module

    monkeypatch.setattr(module.pytesseract, "get_languages", lambda config="": ["eng", "deu"])
    monkeypatch.setattr(module.pytesseract, "image_to_data", lambda *args, **kwargs: data or fake_data())
    monkeypatch.setattr(module.pytesseract, "get_tesseract_version", lambda: "5.4.1")


def test_recognize_maps_text_geometry_and_engine_confidence(monkeypatch) -> None:
    patch_engine(monkeypatch)
    result = TesseractOCRAdapter().recognize(make_image(), OCROptions())
    assert result.text == "Invoice No"
    assert len(result.lines) == 1
    assert [word.text for word in result.lines[0].words] == ["Invoice", "No"]
    assert result.lines[0].words[0].bounds is not None
    assert result.lines[0].words[0].bounds.x == 10
    assert result.confidence == 85.0
    assert result.confidence_kind == "engine_score"
    assert result.engine_id == "tesseract"
    assert result.engine_version == "5.4.1"


def test_recognize_passes_language_and_safe_options(monkeypatch) -> None:
    import app.services.ocr.adapters.tesseract_adapter as module

    patch_engine(monkeypatch)
    calls = {}

    def capture(*args, **kwargs):
        calls.update(kwargs)
        return fake_data()

    monkeypatch.setattr(module.pytesseract, "image_to_data", capture)
    TesseractOCRAdapter().recognize(
        make_image(), OCROptions(languages=("eng", "deu"), page_segmentation_mode="6")
    )
    assert calls["lang"] == "eng+deu"
    assert calls["config"] == "--psm 6 -c preserve_interword_spaces=1"


def test_missing_language_pack_returns_stable_error(monkeypatch) -> None:
    import app.services.ocr.adapters.tesseract_adapter as module

    monkeypatch.setattr(module.pytesseract, "get_languages", lambda config="": ["eng"])
    with pytest.raises(ApplicationError) as error:
        TesseractOCRAdapter().recognize(make_image(), OCROptions(languages=("ind",)))
    assert error.value.code == "OCR_LANGUAGE_UNAVAILABLE"


@pytest.mark.parametrize("options", [
    OCROptions(languages=()),
    OCROptions(languages=("eng; malicious",)),
    OCROptions(page_segmentation_mode="14"),
])
def test_rejects_invalid_options(options) -> None:
    with pytest.raises(ApplicationError) as error:
        TesseractOCRAdapter().recognize(make_image(), options)
    assert error.value.code == "OCR_OPTIONS_INVALID"


def test_rejects_invalid_image_bytes() -> None:
    with pytest.raises(ApplicationError) as error:
        TesseractOCRAdapter().recognize(ImageInput(b"not an image", "image/png"), OCROptions())
    assert error.value.code == "OCR_IMAGE_DECODE_FAILED"


def test_rejects_empty_image() -> None:
    with pytest.raises(ApplicationError) as error:
        TesseractOCRAdapter().recognize(ImageInput(b"", "image/png"), OCROptions())
    assert error.value.code == "OCR_INPUT_INVALID"


def test_rejects_media_type_mismatch() -> None:
    source = make_image()
    with pytest.raises(ApplicationError) as error:
        TesseractOCRAdapter().recognize(
            ImageInput(source.data, "image/jpeg"), OCROptions()
        )
    assert error.value.code == "OCR_MEDIA_TYPE_MISMATCH"


def test_enforces_pixel_limit() -> None:
    with pytest.raises(ApplicationError) as error:
        TesseractOCRAdapter(ResourceLimits(max_image_pixels=10)).recognize(
            make_image(), OCROptions()
        )
    assert error.value.code == "OCR_IMAGE_PIXEL_LIMIT"


def test_enforces_file_size_limit() -> None:
    with pytest.raises(ApplicationError) as error:
        TesseractOCRAdapter(ResourceLimits(max_file_bytes=1)).recognize(
            make_image(), OCROptions()
        )
    assert error.value.code == "OCR_FILE_SIZE_LIMIT"


def test_engine_not_found_maps_to_safe_error(monkeypatch) -> None:
    import app.services.ocr.adapters.tesseract_adapter as module

    def missing(*args, **kwargs):
        raise module.TesseractNotFoundError()

    monkeypatch.setattr(module.pytesseract, "get_languages", missing)
    with pytest.raises(ApplicationError) as error:
        TesseractOCRAdapter().recognize(make_image(), OCROptions())
    assert error.value.code == "OCR_ENGINE_UNAVAILABLE"


def test_empty_engine_output_has_unavailable_confidence(monkeypatch) -> None:
    patch_engine(monkeypatch, data={"text": [], "conf": []})
    result = TesseractOCRAdapter().recognize(make_image(), OCROptions())
    assert result.text == ""
    assert result.lines == ()
    assert result.confidence is None
    assert result.confidence_kind == "unavailable"


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True])
def test_rejects_invalid_execution_timeout(timeout) -> None:
    with pytest.raises(ValueError):
        TesseractOCRAdapter(timeout_seconds=timeout)
