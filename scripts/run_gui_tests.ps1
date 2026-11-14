$ErrorActionPreference = "Stop"
$env:QT_QPA_PLATFORM = "offscreen"

uv run python scripts/verify_environment.py --require-pyside6 --require-qt-offscreen
if ($LASTEXITCODE -ne 0) { throw "PySide6 environment verification failed." }

uv run pytest -v tests/gui tests/unit/test_application_window.py tests/unit/test_feature_configuration_ui.py
if ($LASTEXITCODE -ne 0) { throw "GUI tests reported failures." }
