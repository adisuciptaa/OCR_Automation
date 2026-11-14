$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found. Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
}

uv python install 3.12
if ($LASTEXITCODE -ne 0) { throw "Failed to install Python 3.12 through uv." }

uv lock
if ($LASTEXITCODE -ne 0) { throw "Failed to resolve the project lockfile." }

uv lock --check
if ($LASTEXITCODE -ne 0) { throw "uv.lock is not synchronized with pyproject.toml." }

uv sync --locked --all-groups
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

$env:QT_QPA_PLATFORM = "offscreen"
uv run python scripts/verify_environment.py --require-pyside6 --require-qt-offscreen
if ($LASTEXITCODE -ne 0) { throw "Python/PySide6 environment verification failed." }

Write-Host "OCR Automation Python 3.12 + PySide6 test environment is ready." -ForegroundColor Green
