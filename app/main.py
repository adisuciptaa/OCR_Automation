"""Process entry point for OCR Automation."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from app.bootstrap import bootstrap_application
from app.core.exceptions import ApplicationError


def main(argv: Sequence[str] | None = None) -> int:
    """Start the desktop application and return its process exit code."""
    arguments = list(sys.argv if argv is None else argv)

    try:
        application, main_window = bootstrap_application(arguments)
        main_window.show()
        return application.exec()
    except ApplicationError as exc:
        if exc.code in {"AUTH_SETUP_CANCELLED", "AUTH_LOGIN_CANCELLED"}:
            return 0
        logging.exception("OCR Automation failed during application startup or shutdown.")
        return 1
    except Exception:
        # Last-resort process boundary: preserve diagnostics without exposing
        # implementation details in a GUI dialog at this early foundation stage.
        logging.exception("OCR Automation failed during application startup or shutdown.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
