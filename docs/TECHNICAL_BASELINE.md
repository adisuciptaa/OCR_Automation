# OCR Automation — Technical Baseline

**Baseline:** 2.0.2 (Stage 12 Excel adapter)  
**Architecture:** Modular Feature Management v2.0.0  
**Date:** 2026-11-13  
**Status:** Core, Stage 10 PDF/image adapters, Stage 11 Tesseract OCR adapter, and Stage 12 openpyxl Excel adapter implemented; dependency lock pending regeneration on Python 3.12.

## 1. Approved decisions

| Area | Baseline |
|---|---|
| Language/runtime | CPython 3.12.x |
| Dependency manager | uv |
| GUI | PySide6 |
| Initial deployment | Windows desktop |
| Operating mode | Offline-first |
| Local persistence | SQLite |
| Architecture | Modular Feature Management v2.0.0 |

## 2. Python policy

- `.python-version` pins the project's requested interpreter to `3.12`.
- `requires-python = ">=3.12,<3.13"` constrains dependency resolution to Python 3.12.
- Python 3.15 installed globally on a developer workstation may remain installed.
- The project environment must be created and managed by uv.
- Do not rely on whichever `python` happens to appear first on PATH.

## 3. Dependency policy

- `pyproject.toml` is the source of truth for direct dependencies and development tools.
- `uv.lock` is generated and maintained by uv; never edit it manually.
- Commit `uv.lock` after successful resolution and verification on the target platform.
- Keep runtime dependencies separate from development dependencies.
- Add OCR, PDF, image, Excel, database migration, and packaging dependencies only after
  documenting ownership, purpose, compatibility, license, offline distribution impact,
  and tests.
- Prefer prebuilt Windows wheels where appropriate; document any native runtime/model
  requirements.

## 4. Initial dependencies

Runtime:
- PySide6 — desktop GUI framework.
- pypdfium2/PDFium — PDF inspection, rendering, and embedded-text extraction (BSD-3-Clause / Apache-2.0 dependency licensing; selected to avoid PyMuPDF AGPL/commercial dual-license implications).
- Pillow — image decoding, EXIF orientation handling, and PNG encoding.
- pytesseract — Python adapter interface to the locally installed Tesseract executable; not an OCR engine binary or language model.
- OpenCV headless — image deskew, denoising, and contrast enhancement.
- NumPy — image array representation used by OpenCV adapter.\n- openpyxl — `.xlsx`/`.xlsm` workbook parsing and writing behind `ExcelService` (MIT).

Development:
- pytest — automated tests.
- Ruff — linting and formatting/tooling baseline.

SQLite uses Python's standard-library `sqlite3` module and does not require a third-party
package for basic connectivity.

## 5. Windows setup

```powershell
uv --version
uv python install 3.12
uv lock
uv sync
uv run python --version
uv run python -c "import PySide6; print(PySide6.__version__)"
uv run pytest
uv run ruff check .
```

Expected interpreter output begins with `Python 3.12`.

## 6. Offline deployment implications

Development dependency resolution may require internet access. Offline runtime is a
separate acceptance requirement. Before claiming offline installation, validate that
the installer includes all required wheels/binaries, Qt runtime components, OCR models,
language data, and any native dependencies.

## 7. Deferred decisions

- Tesseract executable and language/model distribution for offline Windows deployment.
- Advanced Excel workbook feature compatibility and representative customer-template validation.
- Database migration tool.
- Windows packaging/installer tool.
- Code signing and update mechanism.
- Exact pinned dependency versions and lockfile (Stage 12 dependency declarations are present, but the lock must be regenerated on the pinned Python 3.12 build host).

These decisions require targeted compatibility tests and must not be guessed.


## Stage 12 — Excel adapter selection

`openpyxl` is selected for `.xlsx` and `.xlsm` workbook inspection and controlled updates.
The library is isolated behind `ExcelService`; feature modules consume only typed public
models. The adapter uses temporary output, verification, and atomic promotion. The
selection does not imply lossless support for every Excel feature. The exact dependency
lock and Windows offline wheel bundle remain release gates.
