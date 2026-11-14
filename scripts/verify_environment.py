"""Verify the supported Python and PySide6 test runtime."""
from __future__ import annotations

import argparse
import importlib.metadata
import os
import platform
import sys

REQUIRED_DISTRIBUTIONS = (
    "PySide6",
    "cryptography",
    "pypdfium2",
    "Pillow",
    "opencv-python-headless",
    "numpy",
    "pytesseract",
    "openpyxl",
    "pytest",
    "ruff",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-pyside6", action="store_true")
    parser.add_argument("--require-qt-offscreen", action="store_true")
    args = parser.parse_args()

    print(f"Python: {platform.python_version()} ({sys.executable})")
    if sys.version_info[:2] != (3, 12):
        print("ERROR: OCR Automation requires Python 3.12.x for supported validation.")
        return 1

    missing: list[str] = []
    for distribution in REQUIRED_DISTRIBUTIONS:
        try:
            version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            missing.append(distribution)
        else:
            print(f"{distribution}: {version}")

    if missing:
        print("ERROR: Missing distributions: " + ", ".join(missing))
        return 1

    if args.require_pyside6 or args.require_qt_offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import qVersion
            from PySide6.QtWidgets import QApplication, QLabel
        except ImportError as exc:
            print(f"ERROR: PySide6 import failed: {exc}")
            return 1

        print(f"Qt runtime: {qVersion()}")
        if args.require_qt_offscreen and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            print("ERROR: QT_QPA_PLATFORM must be set to 'offscreen'.")
            return 1
        if args.require_qt_offscreen:
            try:
                application = QApplication.instance() or QApplication(["ocr-automation-ci"])
                widget = QLabel("Qt offscreen smoke test")
                widget.show()
                application.processEvents()
                if not widget.isVisible():
                    raise RuntimeError("Qt widget did not become visible in offscreen mode.")
                widget.close()
                application.processEvents()
            except Exception as exc:  # Qt plugin/runtime failures must fail the environment check.
                print(f"ERROR: Qt offscreen smoke test failed: {exc}")
                return 1
            print("Qt offscreen smoke test: OK")

    print("Environment verification: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
