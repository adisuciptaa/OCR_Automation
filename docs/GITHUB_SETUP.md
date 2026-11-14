# GitHub Setup — OCR Automation

## 1. Create the repository

1. Sign in to GitHub and create a new repository named `OCR_Automation`.
2. Set visibility to **Private** unless the source code is intentionally approved for public release.
3. Do not initialize the remote repository with a README, license, or `.gitignore`; those files are already present in this project.
4. Do not upload customer PDFs, completed invoices, production workbooks, local databases, OCR model binaries, credentials, or signing private keys.

## 2. Push the Stage 13.8 project

Extract the Stage 13.8 ZIP. Open PowerShell in the extracted `OCR_Automation` repository root and run:

```powershell
git init -b main
git add .
git status
git commit -m "Stage 13.8: add Windows Python 3.12 CI"
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/OCR_Automation.git
git push -u origin main
```

Replace `<YOUR_GITHUB_USERNAME>` with the GitHub account or organization that owns the repository. Review `git status` before committing to ensure no local or sensitive files are staged.

If Git asks for authentication, use GitHub's supported browser sign-in or a configured Git credential manager. Do not put a personal access token in the remote URL or source files.

## 3. Confirm the first CI run

1. Open the repository's **Actions** tab.
2. Select **Windows Python 3.12 CI**.
3. Open the run triggered by the initial push.
4. Review the environment verification, Ruff, compile, and complete pytest steps.
5. Download `pytest-report-windows-python312` to inspect the JUnit report.
6. Download `uv-lockfile-windows-python312`. The incoming Stage 13.7 lockfile was stale; the first run resolves a current lockfile for the Windows Python 3.12 environment.
7. Replace the repository's `uv.lock` with the artifact, then commit and push it:

```powershell
git add uv.lock
git commit -m "Lock dependencies for Python 3.12"
git push
```

After that commit, the CI summary should state that the committed lockfile is synchronized. If the workflow refreshes it again, investigate the dependency metadata and commit the new lockfile deliberately.

## 4. Day-to-day development

- Push changes to `main` to run CI automatically.
- For safer development, create a branch and open a pull request; CI runs on the pull request.
- Do not merge a pull request while environment verification, Ruff, compilation, or tests fail.
- Keep `pyproject.toml` and `uv.lock` changes in the same commit/PR.
- The workflow requires no repository secrets for its current test tasks.
- Use the JUnit artifact and GitHub Actions run URL as evidence in each stage's validation record.

## 5. What CI does not prove

A green CI run proves the automated suite passed on the GitHub-hosted Windows runner with Python 3.12 and PySide6. It does not prove that the app has been visually inspected on the user's own display, that Tesseract is installed with the required language packs on the user's workstation, or that every customer-specific PDF/Excel workbook is supported. Those remain separate acceptance checks using approved synthetic or redacted test data.
