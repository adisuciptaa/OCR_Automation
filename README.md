# OCR Automation

**Repository baseline:** Modular Feature Management Architecture v2.0.0  
**Application package version:** 0.1.3  
**Current milestone:** Stage 13.8 — Testing Infrastructure & Environment Standardization

**API contract version:** 2.15.0

**Validation status:** Stage 13.8 adds a Windows Python 3.12 + PySide6 GitHub Actions workflow, environment verifier, PowerShell setup/test scripts, and offscreen GUI smoke tests. The workflow has not yet been executed against a user-owned GitHub repository. Local development in this session uses Python 3.13.5 and has no PySide6 installation, so Python 3.12/Qt runtime results must come from the first Windows CI run. The incoming `uv.lock` was stale relative to `pyproject.toml`; the first setup/CI run resolves it and provides the refreshed lockfile as an artifact to commit.

## Purpose

OCR Automation is an offline-first Windows desktop application built with Python. It is
designed to process scanned PDF documents, extract structured information, match
extracted values against Excel workbooks, and write validated results to configurable
spreadsheet templates.

## Architecture

The repository follows the approved Modular Feature Management Architecture:

- Application Framework (Core)
- Feature Manager and Feature Registry
- Independently managed Feature Modules
- Reusable Shared Services
- Infrastructure adapters

## Current implementation status

The repository contains the initial PySide6 process entry point and composition root,
the executable Core foundation, and the first Application GUI slice:

- Application lifecycle state management.
- JSON application configuration loading and atomic saving.
- Centralized console and optional rotating-file logging.
- Typed in-process application event bus.
- Service Registry with a read-only `ServiceProvider` view.
- Application runtime startup and shutdown orchestration.
- Main application window with sidebar navigation and page hosting.
- Dashboard with a feature catalog projection and dynamic feature cards.
- Lazy feature workspace delegation through an injected presentation adapter.
- Feature Management page with a read-only projection of persisted Feature Registry records.
- Feature discovery, strict manifest validation, safe ZIP staging, and Ed25519 publisher signature verification.
- SQLite Feature Registry and lifecycle audit persistence.
- Feature lifecycle operations: register, enable, disable, update, and non-destructive uninstall.
- Publisher Registry, Ed25519 public-key management, key rotation/revocation, publisher revocation, and signed-package verification.
- Feature configuration persistence, declarative configuration migrations, isolated feature data migrations, health checks, and verified package rollback.
- Stage 10 pypdfium2/PDFium PDF adapter for metadata inspection, page rendering, normalized region rendering, and embedded text extraction.
- Stage 10 Pillow/OpenCV image adapter for crop, deskew, denoising, and contrast enhancement.
- Stage 11 Tesseract OCR adapter with structured text, line/word geometry, engine confidence, language validation, and bounded execution.
- PDF and image adapters registered through the existing composition-root Service Registry.
- Verified feature entry-point loading with per-activation authorization, integrity, dependency, and license checks.
- Feature initialization, manifest descriptor parity validation, lazy workspace creation, and deterministic shutdown.
- PySide6 workspace adapter with type validation and lifecycle cleanup on disable, update, uninstall, and application shutdown.
- Authorization, service dependency, license, active-job, and package-integrity gates.
- First-run Administrator provisioning, sign-in, scrypt password hashing, account lockout, and session expiry.
- Permission-based RBAC with Administrator, Operator, and Viewer starter roles.
- User administration with role assignment and account activation/deactivation.
- Security audit records for authentication and authorization events.

The following capabilities remain deferred:
- Password recovery, MFA, and remote identity providers.
- Production package verification requires an administrator-provisioned active publisher and Ed25519 public key; the Publisher Registry starts empty by design.
- Lossless compatibility for advanced Excel workbook features beyond the documented adapter support.
- Tax Invoice Reader GUI workspace is implemented in Stage 13.6; detection, extraction, normalization, validation, and configured Excel mapping/output remain feature-owned and are executed through the existing Shared Services.
- Background Job Orchestrator, processing history, and reporting workflows.

## Documentation

See `docs/` for the approved architecture, folder structure, Feature Registry,
API contracts, development standard, changelog, technical baseline, testing guide,
third-party runtime notices, and the GitHub setup guide for the Windows CI workflow.

## Getting started

1. Extract this repository.
2. Install the project-pinned Python 3.12 runtime and `uv`.
3. Run `uv lock` to refresh the dependency lock, then run `uv sync` from the repository root. The initial lock refresh requires package-index access.
4. Run `uv run pytest` and `uv run ruff check .` from the repository root. The pytest configuration adds the repository root to its import path.
5. Start the desktop application with `uv run python -m app.main`. On first launch, create the initial Administrator account, then sign in.

The `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, and other generated
artifacts are local-only and must not be included in source distributions.

## Runtime data

Application configuration and logs are stored under the operating-system-managed
application data directory. The log directory can be overridden with
`OCR_AUTOMATION_LOG_DIR`. The application does not infer persistent data paths from
the current working directory.

## Initial business feature

The first planned business feature is `tax_invoice` (Tax Invoice Reader). It must use
Shared Services through public contracts and must not duplicate generic PDF, OCR,
image, or Excel capabilities.


### Stage 9 — Shared Services Foundation

Public engine-neutral contracts and typed models are established for PDF, OCR, image processing, Excel workbook access, generic validation, and reporting. Stable service IDs are registered through the existing Service Registry.

### Stage 10 — PDF & Image Processing Adapters

- pypdfium2/PDFium implements the PDF service contract for metadata, rendering, normalized clipping, and embedded text.
- Pillow/OpenCV implements image cropping, conservative deskew, denoising, and contrast enhancement.
- Adapters enforce configured resource limits and translate failures into stable application error codes.
- Source PDF and image bytes remain unchanged.

### Stage 11 — OCR Engine Adapter

- Tesseract OCR is exposed through the existing engine-neutral `OCRService` contract using `pytesseract`.
- OCR results include recognized lines, word bounding boxes, engine/version metadata, requested languages, and engine-specific confidence scores.
- The adapter validates encoded image type, media type, size, pixel count, language packs, and page segmentation mode.
- Tesseract execution is bounded by a configurable timeout and vendor exceptions are translated to safe application errors.
- The composition root registers `ocr.recognize`; feature modules continue to consume only the public service contract.
- The Tesseract executable and required language data must be provisioned separately and bundled for offline Windows deployment.

The repository lockfile could not be regenerated in the current environment because the pinned Python 3.12 interpreter is unavailable. Dependency declarations are present in `pyproject.toml`; refresh and verify `uv.lock` in the pinned Python 3.12 build environment before release. Stage 11 additionally requires the Tesseract executable and requested language data to be installed or bundled separately.


### Stage 12 — Excel Engine Adapter

- `OpenpyxlExcelAdapter` implements the existing `ExcelService` contract and is registered
  as `excel.workbook` through the existing Service Registry.
- Supports `.xlsx` and `.xlsm` workbook inspection, worksheet listing, configured record
  reads, mapping-based identifier matching, and verified output writes.
- Supports explicit text/number key types, normalization profiles, duplicate/unmatched
  handling, and overwrite policies.
- Writes to a temporary copy, verifies the staged workbook, and atomically promotes it;
  the source workbook is never used as the output destination.
- Preserves formulas as formulas without evaluating them and writes formula-like extracted
  strings as literal text.
- Advanced workbook features may have round-trip limitations; warnings are returned for
  detectable pivots, drawings, external links, and VBA signature concerns.


### Stage 13.1 — Tax Invoice Feature Contracts

- Added immutable application job request, progress, per-file result, and aggregate result models.
- Added feature-owned Tax Invoice models for raw/normalized identifiers, page detection, and per-PDF extraction outcomes.
- Added the typed Tax Invoice feature execution contract using the existing Feature Runtime contexts.
- MVP identifier scope is limited to the tax invoice number and related invoice number.
- Detection, extraction, configuration manifest, Excel output, and GUI implementation remain in subsequent Stage 13 increments.


### Stage 13.2 — Feature manifest and configuration

- Added `features/tax_invoice/manifest.json` with feature identity, runtime entry point,
  API compatibility, declared Shared Service dependencies, permissions, entitlement,
  configuration schema, and workspace target.
- Added a versioned JSON configuration schema and defaults for page detection, OCR
  preferences, render DPI, and per-document page limits.

### Stage 13.3 — Document detection and extraction

- Added feature-owned marker detection and extraction orchestration using injected PDF/OCR
  public service interfaces.
- Added embedded-text preference, scanned-page top-region OCR, optional full-page fallback,
  page-count limits, and configurable render DPI.
- Added raw extraction for the tax invoice number and related invoice number, preserving
  page index and engine-specific confidence without premature normalization.
- Activated `TaxInvoiceFeature.execute` and per-file `JobResult` adaptation; Excel output and
  GUI workspace remain deferred to Stages 13.5 and 13.6.


### Stage 13.4 — Normalization and validation

- Tax invoice numbers accept 16 ASCII digits or the grouped `000.000-00.00000000` representation; compact values are formatted into the grouped representation.
- Invoice numbers receive Unicode compatibility normalization and all whitespace is removed; case and punctuation are preserved, while raw OCR text remains unchanged.
- Raw extracted values remain available beside normalized values.
- Field validation distinguishes valid, invalid, missing, and conflicting values. Conflicting distinct identifiers require manual review.
- The API contract version is `2.15.0`; no database or configuration-profile migration is required.


### Stage 13.5 — Excel Mapping + Output

- Added optional feature-owned Excel mapping configuration for the source workbook,
  worksheet, key/target columns, match/write identifiers, and duplicate/unmatched/overwrite policies.
- Connected Tax Invoice execution to the existing `excel.workbook` Shared Service.
- Only `success` results are eligible for Excel writes; `review` (displayed as **Need Review**),
  `failed`, and `skipped` results are excluded. Missing required normalized values are downgraded
  to `review` before any write.
- Invoice key matching supports whitespace-removal profiles to align with the feature's
  normalized invoice-number behavior.
- Original workbook remains unchanged; output uses the existing staged-write, verification,
  and atomic-promotion adapter workflow.


### Stage 13.6 — GUI Workspace

- Added the Tax Invoice feature workspace for PDF selection, OCR/detection options, optional Excel mapping, and output destination.
- Runs feature execution on a Qt worker thread; the GUI remains responsive during processing.
- Presents per-file results using exactly three user-facing statuses: **Success**, **Need Review**, and **Failed**. Internal `review` status is preserved, and Stage 13.5 still excludes `review`/`failed`/`skipped` from Excel writes.
- GUI execution must be verified on the supported Python 3.12 + PySide6 desktop environment; the current development environment does not include PySide6.


### Stage 13.7 — Integration Testing & Workflow Hardening

- Added end-to-end Tax Invoice feature integration tests using synthetic per-document outcomes and the real OpenPyXL Excel adapter.
- Verified a mixed batch containing Success, Need Review, and Failed documents writes only the successful document, preserves the source workbook, and returns correct aggregate counts.
- Hardened unexpected Excel adapter failures so extracted documents are not left falsely marked Success; affected successful documents become Failed with a stable error code.
- Corrected the zero-row Excel output path: a successful extraction with no matching/writable workbook row becomes Need Review and no output path is reported.
- Corrected the GUI aggregate label so skipped records are included in the displayed Need Review count.
- No public API contract or database schema change was required.

## Development and validation environment

The supported runtime is Python 3.12.x. Install `uv`, then run
`./scripts/setup_test_environment.ps1` and `./scripts/run_all_tests.ps1` from PowerShell.
GitHub Actions runs the complete Windows/Python 3.12/PySide6 test suite on pushes and pull
requests. See `docs/TESTING_GUIDE.md` for lockfile bootstrap, CI artifacts, offscreen GUI
testing, and manual Windows/OCR acceptance checks.

## Local feature installation (Stage 13.8.1)

Feature source code in `features/` is not installed automatically. Use the signed development
package workflow documented in `docs/FEATURE_INSTALLATION_BOOTSTRAP.md` to create a local
publisher key, build a signed ZIP, trust its public key through Feature Management, install,
and enable the feature. Installed packages are stored separately in the OS application-data
folder so package installation never overwrites the editable source tree.
