$ErrorActionPreference = "Stop"
$env:QT_QPA_PLATFORM = "offscreen"

uv run python scripts/verify_environment.py --require-pyside6 --require-qt-offscreen
if ($LASTEXITCODE -ne 0) { throw "Environment verification failed." }

uv run ruff check .
if ($LASTEXITCODE -ne 0) { throw "Ruff reported issues." }

uv run python -m compileall -q app features tests tools scripts
if ($LASTEXITCODE -ne 0) { throw "Python compilation failed." }

New-Item -ItemType Directory -Force -Path tests/reports | Out-Null
uv run pytest -v --junitxml=tests/reports/junit-local-windows-py312.xml
if ($LASTEXITCODE -ne 0) { throw "Pytest reported failures." }

Write-Host "All configured checks passed." -ForegroundColor Green
