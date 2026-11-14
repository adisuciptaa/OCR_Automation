# Changelog

All notable repository and architecture changes should be recorded here.

## [0.1.0] — Technical foundation baseline (2026-11-06)

### Added
- Python 3.12 project pin and compatible Python requirement.
- uv project and dependency management configuration.
- PySide6 as the initial GUI runtime dependency.
- pytest and Ruff development tool groups.
- Basic pytest and Ruff configuration.
- Windows PowerShell setup and verification commands.

### Changed
- Reduced premature empty directory creation; directories are introduced with their
  owning implementation.
- Clarified that the repository is a scaffold and not yet a working application.

### Deferred
- OCR/PDF/image/Excel dependencies pending compatibility, licensing, and offline
  packaging evaluation.
- `uv.lock` generation pending execution of `uv lock` in the development environment.
- Database migration library selection.
- Windows installer/build tool selection.
- Application entry points and executable source code.


## [0.1.1] — Application entry point and bootstrap (2026-11-06)

### Added
- `app/main.py` as the process entry point.
- `app/bootstrap.py` as the composition root for QApplication and the initial window.
- `app/ui/application_window.py` as a minimal Presentation Layer window shell.
- Unit tests for bootstrap composition and process entry-point behavior.
- Python package markers for the implemented application packages.

### Notes
- No Core lifecycle manager, configuration manager, logging subsystem, service registry,
  Feature Manager, authentication, persistence, or OCR workflow was introduced.
- The initial window is intentionally a neutral shell; feature navigation and dashboard
  behavior remain deferred.


## [Unreleased]

### Fixed — Feature licensing and Tax Invoice runtime contract
- Treat a missing `license_entitlement` as an explicit indication that a feature is not
  license-gated; custom license providers are called only for declared entitlement IDs.
- Apply the same entitlement rule during enable, update, runtime lookup, and feature catalog
  projection.
- Set the Tax Invoice runtime descriptor entitlement to `None` to match its manifest, which
  does not declare a license entitlement.
- Add regression tests for unlicensed features, valid declared entitlements, and rejected
  declared entitlements.
- Add a permission-gated Feature Management uninstall action so stale registered packages
  can be cleanly removed and reinstalled; retain package backups through Feature Manager.
- Distinguish Feature Registry read failures from an empty registry in the CMS instead of
  presenting a failed read as “no feature packages registered.”

### Stage 4: Application GUI Development

#### Added
- PySide6 application shell with a consistent application header and sidebar.
- Dashboard overview with feature cards populated only through an injected feature catalog projection.
- Dynamic feature navigation and lazy workspace creation through a presentation adapter.
- Feature Management landing page that clearly reports the Feature Manager backend is not yet connected.
- Settings landing page aligned with the existing Core Configuration Manager boundary.
- Presentation navigation guard and GUI unit tests for page navigation, feature catalog rendering,
  lazy workspace creation, and rejection of unknown feature IDs.

#### Changed
- Updated the API contract with a session-scoped, display-only feature catalog projection (2.1.0).
- Updated the canonical folder structure and README to reflect the implemented GUI.

#### Deferred
- Feature Manager lifecycle operations, authentication/authorization integration, and persistence.
- Feature-specific workspaces until verified feature packages and their adapters are available.
- Job progress, history, and reports until Job Orchestrator and related contracts are implemented.

### Stage 1: Application Core Foundation

#### Added
- Core lifecycle state manager with validated transitions.
- JSON configuration manager with defaults, deep merge, and atomic save.
- Typed in-process event bus with correlation IDs and isolated subscriber failures.
- Service Registry and read-only `ServiceProvider` facade.
- Application runtime startup/shutdown orchestration.
- Centralized console and optional rotating-file logging.
- Unit tests for lifecycle, configuration, events, service resolution, and runtime.

#### Changed
- Bootstrap now composes and initializes Core services before creating the main window.
- Application data/configuration paths use the OS-managed application data directory.
- README and folder ownership documentation now reflect the implemented Core foundation.

#### Deferred
- Feature Manager and Feature Registry runtime implementation.
- Authentication, authorization, persistence, and audit repository implementation.
- OCR/PDF/image/Excel Shared Service adapters and business Feature Modules.

## [Stage 5] - 2026-11-12

### Added
- Feature Manager public contracts and immutable feature/package data models.
- Strict manifest schema and parser, approved-root discovery, and SHA-256 allowlist verifier.
- Safe ZIP package staging/installation with traversal, symlink, compressed/expanded size, and file-count checks; security-invalid archives are preserved in quarantine where size permits.
- SQLite Feature Registry repository and lifecycle audit table/migration.
- Lifecycle transition policy and application service for register, enable, disable, update,
  uninstall, and authorized feature catalog projection.
- Dynamic dashboard catalog adapter and read-only Feature CMS registry listing.
- Unit tests for manifests, package verification, archive handling, lifecycle, persistence,
  authorization projection, and feature lifecycle operations.

### Security / limitations
- Bootstrap uses deny-all authorization and an empty protected-trust allowlist until real
  AuthorizationService and publisher trust provisioning are implemented.
- Feature code loading, feature workspaces, feature configuration persistence, schema migrations,
  and post-update health-check/rollback tooling remain deferred.
- Update rejects data schema version changes, retains prior packages, and supports restoration after failed promotion/persistence. Uninstall retains a verified package backup before removal.


### Stage 6 Authentication & Authorization — 2026-11-12

### Added
- Core Security package with authentication, RBAC authorization, password hashing, and process-local sessions.
- SQLite migration `0002_authentication.sql` for users, roles, permissions, assignments, lockout state, and security audit.
- Interactive first-run Administrator provisioning and mandatory sign-in in the production bootstrap.
- User administration page with account creation, role assignment, and account activation/deactivation.
- Authenticated application header with an explicit Sign out action.
- Scrypt password hashing with unique salts, password policy, constant-time verification, and bounded KDF parameters.
- Five-attempt / 15-minute login lockout and 30-minute idle / 12-hour absolute session expiry.
- Authorization checks for Feature Registry viewing and user administration; Feature Manager now receives the RBAC provider.
- Security unit tests for hashing, setup, login, lockout, RBAC, inactive users, user-management authorization, and sessions.

### Changed
- API contract version advanced from 2.1.0 to 2.2.0 for authentication, session, and persistence contracts.
- Production bootstrap now requires initial setup and sign-in before composing the main workspace.
- Application window and sidebar now project page visibility from the authenticated user's permissions.

### Security notes / limitations
- Password hashing uses Python standard-library scrypt; no new runtime dependency was added.
- Password recovery, MFA, remote identity providers, and LAN/shared sessions remain out of scope.
- Trusted feature publisher digests remain unprovisioned; feature package installation remains fail-closed.
- Encryption-at-rest and protected database backup policy remain deployment-level work.


### Stage 7 — Feature Runtime Loading & Workspace Activation — 2026-11-13

#### Added
- Public `FeatureContext`, `UIContext`, and `FeatureModule` runtime contracts.
- Feature runtime loader using unique per-package module namespaces and package-relative imports.
- Fresh enabled-state, RBAC, package-integrity, dependency, and license checks before activation.
- Restricted feature service-provider facade exposing only manifest-declared service dependencies.
- Runtime descriptor parity validation against the verified feature manifest.
- Lazy feature workspace creation through a Presentation-owned PySide6 adapter.
- Runtime instance reuse and cleanup on disable, update, uninstall, and application shutdown.
- Runtime unit tests covering activation, workspace context, lifecycle unload, descriptor mismatch, and invalid entry points.

#### Changed
- API contract version advanced from 2.2.0 to 2.3.0.
- Bootstrap now composes and injects the Feature Runtime and workspace adapter.
- Main window releases feature runtime resources when closing.

#### Security / limitations
- Feature Python code executes in-process and is not sandboxed. Runtime activation is fail-closed unless the package is enabled, verified, compatible, licensed, and authorized.
- Bootstrap still has an empty trusted publisher digest allowlist, so no third-party feature package can be activated in the default production configuration.
- Feature configuration persistence, data migrations, post-load health checks, OCR/PDF/Excel services, Job Orchestrator, and business workflows remain deferred.


### Stage 7 follow-up — pytest import path

#### Fixed
- Added the repository root to pytest `pythonpath` so tests can import the `app` package consistently when pytest is launched from the repository root on Windows.


### Stage 8.1 — Feature Configuration Manager — 2026-11-13

#### Added
- Feature-scoped configuration models, scopes, and public repository/manager contracts.
- Authorized configuration manager with fail-closed validation for a documented JSON Schema subset, schema defaults, profile reset, and independent `x-config-version` handling.
- SQLite configuration profile repository and migration `0003_feature_configuration.sql`.
- Installation, company, user, and job configuration scopes.
- Feature configuration audit entries and typed update/reset events.
- Unit tests for validation, authorization, scope isolation, persistence, defaults, reset, version mismatch, and secret-field rejection.

#### Changed
- Bootstrap composes and registers `feature.configuration` through the existing Service Registry.
- API contract version advanced from 2.3.0 to 2.4.0.

#### Security / limitations
- Configuration operations fail closed without `feature.configure.<feature_id>`.
- Secret-marked fields are rejected; a dedicated secret store is not part of Stage 8.1.
- Configuration schema version mismatch is blocked pending Stage 8.3 migration support.
- Feature Configuration UI remains Stage 8.2.


### Stage 8.2 — Feature Configuration UI — 2026-11-13

#### Added
- Schema-driven Feature Configuration dialog integrated into Feature CMS.
- Typed controls for string, integer, number, boolean, and enum properties; structured
  JSON editor for array/object/null values.
- Installation, company, user, and job scope selection with installation default key
  and authenticated-user default for user scope.
- Configure actions projected only for actors with the feature-specific configuration
  permission.
- Public immutable schema projection (`FeatureConfigurationSchema`) and authorized
  `get_configuration_schema` manager operation.
- UI tests for schema-driven control generation, typed save values, and scope behavior.

#### Changed
- Feature CMS receives the existing configuration manager and authorization service
  through the application composition root.
- API contract version advanced from 2.4.0 to 2.5.0.

#### Security / limitations
- UI permission visibility is convenience only; the configuration manager continues
  to enforce authorization for every operation.
- Secret-marked fields remain unsupported pending a dedicated secure secret store.
- Structured array/object values are edited as JSON; validation remains authoritative
  in Feature Configuration Manager.


### Stage 8.3 — Feature Data Migration Engine — 2026-11-13

#### Added
- `FeatureDataMigrationEngine` for separately versioned feature configuration and feature-owned data migrations.
- Declarative JSON configuration migration operations: rename field, remove field, set default, and map value.
- Atomic repository migration of all stored configuration profiles for a feature.
- Isolated per-feature SQLite data stores and sequential SQL migration execution.
- Migration history records, pre-migration database backups, fail-closed path checks, SQL restrictions, package digest verification, and migration events.
- Unit tests for configuration migration, missing migration steps, successful SQL migration, SQL transaction rollback, and forbidden SQL controls.

#### Changed
- Bootstrap registers `feature.migrations` through the existing Service Registry.
- API contract version advanced from 2.5.0 to 2.6.0.

#### Limitations
- Automatic package update still rejects `data_schema_version` changes. Stage 8.4 must coordinate package, configuration, and data rollback before enabling end-to-end automatic migrations during package update.
- Feature data migration currently targets isolated SQLite stores; it does not migrate arbitrary external databases or execute Python callbacks.


## [Stage 8.4] — Health Check & Rollback (2026-11-13)

### Added
- Typed feature health status, item, and report models.
- Read-only health checks for package digest/manifest, declared dependencies,
  configuration schema/profile compatibility, and feature-owned SQLite integrity.
- Durable feature package checkpoints with atomically written recovery journals.
- Verified package rollback restoring the prior manifest and Feature Registry record.
- Feature updates create a checkpoint, require a healthy post-update report, and roll
  back automatically when the report is unhealthy.
- Startup recovery discovery for journals left in the prepared state.
- Health, checkpoint, and rollback application events.
- Unit tests for healthy/tampered package diagnostics and verified package rollback.

### Changed
- API contract version advanced to 2.7.0.
- Bootstrap registers `feature.health` and `feature.rollback` through the existing
  Service Registry.
- Architecture, Feature Registry, folder structure, and development standards document
  the health and recovery ownership boundaries.

### Limitations
- Automatic update rollback covers the managed feature package and Feature Registry
  record. It does not claim to reverse arbitrary external side effects.
- Automatic restoration of feature database backups and arbitrary feature side effects
  is not claimed. Database recovery remains coordinated with the Stage 8.3 migration
  backup and requires a separate verified restore operation.
- Startup journal recovery requires trusted package digests. The current empty bootstrap
  trust allowlist remains fail-closed pending Stage 8.5 Publisher Trust Management.


## [Stage 8.5] — Publisher Trust Management (2026-11-13)

### Added
- Publisher Registry with active/revoked publisher lifecycle.
- Ed25519 public-key storage, fingerprint-derived key IDs, multiple-key rotation, and key revocation.
- SQLite publisher trust audit trail and `publisher.manage` permission.
- Publisher Trust Manager with authorized registration, key management, revocation, and listing.
- Signed package verification binding publisher ID, feature ID, version, and package SHA-256 digest.
- Root-level `publisher_signature.json` envelope; only this envelope is excluded from package digest.
- Publisher-side offline signing utility at `tools/sign_feature_package.py`.
- Production bootstrap composition and Service Registry registration for `publisher.trust`.
- Unit tests for valid signatures, tampering, unknown/revoked publishers, key rotation/revocation,
  feature binding, and authorization.

### Changed
- PackageVerifier delegates to Publisher Trust Manager in production bootstrap; there is no
  digest-only fallback in the production trust path.
- Feature manifest accepts optional `publisher_id`; production signature verification requires it.
- API contract version advanced to 2.8.0.
- Architecture, API contracts, Feature Registry, folder structure, and development standards
  document publisher trust ownership and signature format.

### Security / limitations
- Existing unsigned packages and legacy digest-only packages are not accepted by production
  bootstrap; they must be signed by a registered publisher.
- Revocation blocks subsequent verification but does not yet forcibly unload already-running
  feature instances.
- Public-key import is an administrator-controlled local operation; secure out-of-band
  publisher identity verification and key distribution remain operational responsibilities.
- Publisher private-key generation, hardware-backed storage, and signing-key custody are
  publisher-side responsibilities, not application features.


## [Stage 9 — Shared Services Foundation] — 2026-11-13

### Added
- Engine-neutral public Protocol contracts for PDF, OCR, image, Excel, generic validation, and reporting services.
- Immutable typed service models for PDF metadata/rendered pages, OCR inputs/options/results/geometry, Excel workbook/read/write/verification, validation issues, and processing reports.
- Shared `NormalizedRegion`, `ResourceLimits`, and `ServiceMetadata` value objects.
- Stable service identifiers and a typed registration helper that uses the existing Core Service Registry.
- Unit and contract tests for shared model validation and registration/provider access.

### Changed
- API contract version advanced from 2.8.0 to 2.9.0.
- API contracts, folder structure, and development standards document Shared Services ownership and contracts.

### Deferred / limitations
- Production PDF, OCR, image, and Excel adapters are not included in this foundation stage. No new runtime dependency was added.
- Shared service registration helper is ready for the composition root but is not activated in production bootstrap until concrete adapters are selected and validated.
- Validation and reporting contracts are established; concrete persistence/export behavior remains deferred.


## [Stage 10 — PDF & Image Processing Adapters] — 2026-11-13

### Added
- `PdfiumAdapter` implementing PDF inspection, page rendering, normalized-region rendering, and embedded text extraction.
- `OpenCVImageAdapter` implementing normalized cropping, conservative deskew, bilateral denoising, and CLAHE contrast enhancement.
- Input validation and configured byte, page, DPI, and pixel resource limits, including preflight render-pixel estimation.
- Stable PDF/image adapter error codes and safe exception translation.
- Composition-root registration for `pdf.render` and `image.process`.
- Unit tests using generated PDF and image fixtures; no customer documents or OCR model assets required.

### Changed
- Added pypdfium2, Pillow, OpenCV headless, and NumPy runtime dependencies. pypdfium2/PDFium was selected instead of PyMuPDF to avoid the latter’s AGPL/commercial dual-license implications for a potentially commercial desktop distribution.
- API contract version advanced from 2.9.0 to 2.10.0 to document Stage 10 adapter behavior and stable errors.
- Updated architecture, folder structure, Feature Registry service inventory, development standards, technical baseline, third-party notices, and README.

### Limitations
- OCR and Excel concrete adapters remain deferred.
- Encrypted PDFs are rejected; password-based PDF decryption is not part of the current public contract.
- Deskew intentionally skips ambiguous or extreme angle estimates.
- Offline installation requires the selected wheels and their transitive dependencies to be included in the release bundle; this source-stage change alone does not prove an offline installer is complete.


## [Stage 11 — OCR Engine Adapter] — 2026-11-13

### Added
- Tesseract-backed `TesseractOCRAdapter` implementing the existing `OCRService` contract.
- OCR image validation for supported formats, declared media type, file size, decoded pixel count, and corrupt input.
- Language-pack and page-segmentation option validation, bounded engine execution, and safe structured errors.
- Structured OCR text, line grouping, word bounding boxes, engine metadata, and explicitly engine-specific confidence scores.
- Unit tests that mock the Tesseract boundary and do not require a local OCR executable.

### Changed
- Composition-root registration now provides `ocr.recognize` alongside the existing PDF and image services.
- Added `pytesseract` as the Python wrapper dependency; the native Tesseract executable and language data remain separate deployment assets.
- API contract version advanced to 2.11.0 without changing the public OCR Protocol or data model signatures.
- Application package version advanced to 0.1.2.
- Updated README, architecture, API contracts, folder structure, technical baseline, testing guide, and third-party runtime notices.

### Limitations
- The OCR adapter requires a compatible Tesseract executable and requested language data installed locally. These assets are not bundled by `pytesseract`.
- The Stage 11 environment does not establish production Windows offline packaging; that remains a release validation requirement.
- Confidence is the arithmetic mean of Tesseract word scores and is not a calibrated probability.


## [Stage 12 — Excel Engine Adapter] — 2026-11-13

### Added
- `OpenpyxlExcelAdapter` implementing the existing engine-neutral `ExcelService` contract.
- `.xlsx` and `.xlsm` workbook inspection, worksheet metadata, configured record reading,
  and workbook verification.
- Mapping-based key matching with text/number key types, explicit normalization profiles,
  duplicate policies, unmatched policies, and overwrite policies.
- Safe staged workbook writes with source immutability, output verification, and atomic
  promotion to the requested destination.
- Literal handling for formula-like extracted strings; workbook formulas are not evaluated.
- Unit and Service Registry contract tests for the Excel adapter.

### Changed
- Composition-root registration now includes `excel.workbook` version `1.0.0`.
- Added `openpyxl` as a runtime dependency.
- Application package version advanced to `0.1.3`.
- API contract version advanced to `2.12.0`.
- Updated architecture, API contracts, Feature Registry service inventory, folder structure,
  development standards, README, technical baseline, testing guide, and third-party notices.

### Limitations
- `.xls`, `.xlsb`, and encrypted workbooks are unsupported.
- openpyxl does not guarantee lossless preservation of all advanced workbook features.
  Pivot tables, drawings/charts/images, external links, macro signatures, and embedded
  objects require representative workbook validation.
- The Stage 12 runtime dependency lock could not be regenerated in the current Python 3.13
  environment; regenerate and verify `uv.lock` using the project-pinned Python 3.12 build
  environment before release.


## [Stage 13.1] — Tax Invoice Feature Contracts — 2026-11-14

### Added
- Immutable application-level `JobRequest`, `JobProgress`, `FileResult`, and `JobResult`
  contracts in `app/core/job_contracts.py`.
- Tax Invoice feature models for raw/normalized identifier values, page detection, and
  per-document extraction outcomes.
- Typed `TaxInvoiceFeatureContract` based on the existing Feature Runtime contexts.
- Unit tests for job contract invariants and Tax Invoice model validation.

### Changed
- API contract version advanced from 2.12.0 to 2.13.0 for additive job and feature contracts.
- Documented Tax Invoice package ownership and Stage 13.1 implementation boundaries.

### Validation
- Stage 13.1 targeted tests: 14 passed in the current Python 3.13.5 environment.
- Non-GUI regression suite: 166 passed, 1 skipped in the current environment.
- Three PySide6-dependent GUI/bootstrap modules were excluded because PySide6 is unavailable.
- Python 3.12 verification of the new Stage 13.1 code remains to be repeated by the project owner.


## [Stage 13.2] — Tax Invoice Manifest and Configuration — 2026-11-14

### Added
- Manifest-backed `tax_invoice` feature metadata with declared runtime entry point,
  workspace target, compatibility version, permissions, entitlement, and exact Shared
  Service dependency versions.
- Version 1 configuration schema for detection, OCR preferences, and document processing
  limits, compatible with the existing Feature Configuration Manager's supported schema
  subset.
- Feature configuration defaults and lifecycle entry-point shell. Execution and the GUI
  workspace intentionally remain deferred to Stages 13.3 and 13.6.
- Tests for manifest loading, declared service dependencies, schema/default validation,
  invalid configuration rejection, independent defaults, and descriptor parity.

### Changed
- Corrected `app.API_CONTRACT_VERSION` to `2.13.0`, matching the Stage 13.1 API contract
  documentation and runtime compatibility checks.
- Updated feature documentation, canonical folder structure, and README milestone.

### Validation
- Stage 13.2 targeted tests: 6 passed in the current Python 3.13.5 environment.
- Python 3.12 and full GUI regression verification remain pending in the project owner's
  pinned environment; PySide6 is unavailable in the current implementation environment.
- The development ZIP is not claimed to be signed or production-installable.


## [Stage 13.3] — Tax Invoice Detection and Extraction — 2026-11-14

### Added
- Feature-owned marker matching and page-candidate detection in `detector.py`.
- PDF metadata inspection, embedded-text preference, top-region scanned-page OCR, optional
  full-page fallback, and full-page OCR extraction orchestration in `extractor.py`.
- Raw extraction for `tax_invoice_number` and `invoice_number`, retaining source page and
  engine-specific OCR confidence without applying Stage 13.4 normalization rules.
- Per-file execution result adaptation through the existing application `JobRequest` and
  `JobResult` contracts.
- Detection/extraction unit tests using fake PDF and OCR services.

### Changed
- Tax Invoice configuration schema added optional configurable `render_dpi` while retaining schema version 1 for backward compatibility
  (default 200, range 100–400).
- `TaxInvoiceFeature.execute` now validates configuration, resolves the injected PDF/OCR
  services, isolates per-file failures, and returns structured job outcomes.
- Updated API contract, Feature Registry documentation, folder structure, feature guide,
  and repository README for Stage 13.3 behavior and limitations.

### Validation
- Stage 13.3 targeted feature and job-contract tests: 27 passed in Python 3.13.5.
- Non-GUI regression suite: 166 passed, 1 skipped (the PySide6-dependent test was skipped).
- `python -m compileall -q app features tests tools` completed successfully.
- Ruff could not be run because the Ruff package is not installed in the environment.
- ZIP integrity check completed successfully; archive SHA-256 is recorded in the Stage 13.3 delivery note.
- PySide6 GUI/bootstrap test modules and Python 3.12 verification remain unavailable in
  the current development environment.


## [Stage 13.4] — Tax Invoice Normalization and Validation — 2026-11-14

### Added
- Conservative normalization for tax invoice identifiers and issuer-defined invoice numbers.
- Field-level validation states (`valid`, `invalid`, `missing`, `conflict`) and document-level validation summary.
- Detection of conflicting identifier values across candidate-page OCR/embedded-text occurrences.
- Unit tests for accepted/rejected formats, whitespace normalization, missing values, and conflicts.

### Changed
- Tax Invoice extraction now populates normalized values only after validation while preserving raw OCR text.
- Per-file job results include a structured validation summary.
- API contract version advanced from 2.13.0 to 2.14.0 for the additive validation result contract.
- Updated feature documentation, Feature Registry compatibility metadata, and README milestone.

### Validation
- Stage 13.4 targeted Tax Invoice, normalization, validation, and job-contract tests: 35 passed in Python 3.13.5.
- Non-GUI regression suite: 166 passed, 1 skipped (PySide6-dependent test).
- `python -m compileall -q app features tests tools` completed successfully.
- Ruff could not be run because it is not installed in the environment.
- Three GUI/bootstrap modules were excluded because PySide6 is unavailable; Python 3.12 verification remains required in the project's pinned environment.
- ZIP integrity check completed successfully; this development package is not signed or claimed production-installable.


## [Stage 13.4 Revision 1] — Invoice Number Whitespace Normalization — 2026-11-14

### Changed
- Invoice number `normalized_value` now removes all whitespace characters, including spaces, tabs, and line breaks.
- Case and punctuation remain unchanged; the original OCR candidate remains preserved in `raw_value`.

### Tests
- Added coverage for ordinary spaces, non-breaking spaces, tabs, and line breaks in invoice identifiers.


## [Stage 13.5] — Tax Invoice Excel Mapping and Output — 2026-11-14

### Added
- Optional Tax Invoice Excel mapping configuration for source workbook, worksheet, header/data
  rows, source key and target columns, match/write identifiers, and write policies.
- Feature-owned Excel output orchestration using the existing `excel.workbook` Shared Service.
- Strict write eligibility: only `success` file results are sent to Excel. `review` (display
  label **Need Review**), `failed`, and `skipped` results are never written.
- Tests proving review/failed exclusion, missing normalized-field downgrade to review, and
  successful mapping output.
- Generic Excel key normalization profiles `remove_whitespace` and
  `remove_whitespace_casefold` for matching invoice keys without whitespace.

### Changed
- API contract version advanced from 2.14.0 to 2.15.0 for the additive Excel matching
  normalization profiles and Tax Invoice mapping/output behavior.
- `TaxInvoiceFeature.execute` optionally inspects, reads, maps, writes, verifies, and reports
  the destination workbook through the injected Excel service.
- Invoice-number matching defaults to the `remove_whitespace` normalization profile when
  configured, consistent with Stage 13.4 invoice normalized values.
- The original workbook remains immutable; the requested job output path is a separate file.
- Updated Feature Registry, API contracts, folder structure, feature guide, and README.

### Validation
- Stage 13.5 targeted Excel mapping, write-eligibility, Tax Invoice, and job-contract tests: 58 passed in Python 3.13.5.
- Non-GUI regression suite: 167 passed, 1 skipped; three GUI/bootstrap modules were excluded because PySide6 is unavailable, and one PySide6-dependent test was skipped.
- `python -m compileall -q app features tests tools` completed successfully.
- Ruff could not be run because it is not installed in the environment.
- Python 3.12 verification remains pending in the project's pinned target environment.


## [Stage 13.6] — Tax Invoice GUI Workspace — 2026-11-14

- Implemented the manifest-declared Tax Invoice PySide6 workspace with multi-PDF selection,
  processing controls, optional Excel mapping, output destination selection, and result details.
- Added a dedicated Qt worker thread so PDF/OCR/validation/Excel operations do not run on the GUI thread.
- Added the three requested user-facing result statuses: Success, Need Review, and Failed;
  internal `review` and Stage 13.5 Excel write-eligibility behavior remain unchanged.
- Added a feature execution lock so feature shutdown waits for an active worker execution before
  releasing its injected service context.
- Documented workspace ownership and execution behavior. No API contract version or database
  schema change was required.
- GUI runtime verification remains pending because PySide6 is not installed in the current
  development environment; compile and non-GUI regression checks are recorded separately.


## [Stage 13.7] — Integration Testing & Workflow Hardening — 2026-11-14

### Added
- Added end-to-end mixed-batch integration coverage using synthetic PDF outcomes and the real OpenPyXL adapter.
- Verified only successful extraction results are written to Excel; Need Review and Failed results remain excluded.
- Verified the source workbook remains byte-for-byte unchanged while the output workbook receives the successful value.
- Added integration coverage for zero matching/writable Excel rows and unexpected adapter failures.

### Changed
- Successful extraction results are downgraded to `review` when Excel reports that zero rows were written; the output path is withheld.
- Unexpected non-contract Excel adapter exceptions are contained at the feature boundary and convert affected successful files to `failed` with `TAX_INVOICE_EXCEL_OUTPUT_FAILED`.
- GUI Need Review aggregate now consistently includes internal `skipped` results, matching their displayed status label.
- Added Stage 13.7 integration and hardening guidance to the Testing Guide.
- No API contract version or database schema increment was required.

### Validation
- Stage 13.7 targeted integration, Tax Invoice feature, and Excel adapter tests: 58 passed in Python 3.13.5.
- Stage 13.7 targeted integration, Tax Invoice feature, and Excel adapter tests: 58 passed in Python 3.13.5.
- Non-GUI regression suite: 170 passed, 1 skipped. The three GUI/bootstrap test modules were excluded because PySide6 is unavailable; one PySide6-dependent module was skipped.
- `python -m compileall -q app features tests tools` and JSON manifest/schema parsing completed successfully.
- Ruff and Python 3.12 are unavailable in this environment. GUI runtime verification remains pending on the pinned Python 3.12 + PySide6 Windows environment.


## [Stage 13.8] — Testing Infrastructure & Environment Standardization — 2026-11-14

### Added
- Added Windows GitHub Actions CI for Python 3.12, PySide6, Ruff, compile checks, and the
  complete pytest suite without GUI/bootstrap exclusions.
- Added a Python/PySide6/Qt offscreen environment verifier.
- Added PowerShell scripts for environment setup, full validation, and GUI-focused tests.
- Added offscreen Tax Invoice workspace tests covering widget construction and projection of
  internal success/review/failed/skipped outcomes into the three user-facing statuses.
- Added CI artifact publication for JUnit test reports and the resolved dependency lockfile.

### Changed
- Expanded Testing Guide, Development Standard, Folder Structure, and README with the
  supported Python 3.12 workflow, lockfile policy, GitHub Actions procedure, and CI acceptance
  rules.
- Added a GitHub setup guide covering private repository creation, first push, CI artifact
  retrieval, lockfile bootstrap, and day-to-day branch/pull-request workflow.
- Added generated test-report paths to `.gitignore`.
- No application API contract or database schema change was required.

### Validation
- Source compilation and repository hygiene checks are performed in the current development
  environment; this environment is Python 3.13.5 and does not have PySide6.
- Python 3.12 + PySide6 GUI execution and the Windows GitHub Actions workflow remain pending
  the first run in the user's GitHub repository.
- The Stage 13.7 incoming `uv.lock` metadata was found stale against `pyproject.toml`; setup
  and CI resolve it and publish the refreshed lockfile artifact. The refreshed lockfile must be
  committed before subsequent CI runs are considered fully reproducible.

## Stage 13.8.1 — Feature Packaging & Installation Bootstrap

- Separated editable source modules (`features/`) from installed packages in the OS-managed
  application data directory (`features/installed/`).
- Added local Ed25519 development publisher key generation and signed feature ZIP packaging.
- Added authenticated Feature Management actions to trust a publisher, install a signed ZIP,
  and enable a registered feature.
- Preserved manifest, compatibility, dependency, authorization, and publisher signature checks.
- Added `docs/FEATURE_INSTALLATION_BOOTSTRAP.md` with local setup and verification steps.
