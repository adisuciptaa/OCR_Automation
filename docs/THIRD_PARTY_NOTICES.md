# Third-Party Runtime Notices — Stages 10–12

This inventory records the direct Stage 10 PDF and image-processing runtime dependencies. It is a planning/notice aid, not legal advice and not a substitute for shipping the complete license and attribution files supplied by each exact resolved wheel.

| Distribution | Purpose | Declared license family | Release requirement |
|---|---|---|---|
| `pypdfium2` / PDFium | PDF metadata, page rendering, embedded text | BSD-3-Clause / Apache-2.0; PDFium and bundled component notices must be retained | Include the exact wheel's license/notice files and verify all bundled PDFium notices. |
| `Pillow` | Image decoding, EXIF orientation, PNG encoding | HPND-style permissive license | Include the license text supplied by the resolved Pillow distribution. |
| `opencv-python-headless` | Deskew, denoising, contrast enhancement | Apache License 2.0 | Include Apache-2.0 license and required notices. |
| `numpy` | Image array representation | BSD-3-Clause, with separately licensed bundled components in some wheels | Include NumPy and bundled-component notices from the exact wheel. |\n| `openpyxl` | XLSX/XLSM workbook parsing and writing | MIT | Include the license text supplied by the exact resolved distribution and review transitive dependencies. |

## Selection note

`pypdfium2` was selected instead of PyMuPDF because PyMuPDF is dual-licensed under AGPL-3.0 or a commercial Artifex license. The selected PDFium route avoids introducing that AGPL/commercial licensing decision into this stage. This does not remove the need to inspect and preserve PDFium's bundled third-party notices.

## Release gate

Before commercial or offline distribution:

1. Resolve and pin exact dependency versions in `uv.lock` on the supported Python 3.12 build environment.
2. Generate a complete software bill of materials from the resolved environment.
3. Extract and include all license/NOTICE files from the exact Windows wheels, including transitive and bundled native components.
4. Re-run dependency/license review whenever any dependency or version changes.
5. Confirm that the offline installer contains all required wheels and native runtime components.


## Stage 11 deployment notice

`pytesseract` does not bundle the Tesseract OCR executable or trained language data. The Windows installer must provision a compatible Tesseract build and the selected `.traineddata` files. Record the exact engine build, language-data versions, and all upstream license/notice files in the release SBOM. Do not claim offline OCR support until a clean offline Windows installation has been tested.


## Stage 12 Excel deployment notice

`openpyxl` is a pure-Python workbook engine declared as a runtime dependency. Resolve
and pin its exact version and transitive dependencies on Python 3.12, include compatible
Windows wheels in the offline installer, and ship the exact distribution license notices.
Do not infer that the workbook adapter is offline-deployment-ready from the dependency
declaration alone.
