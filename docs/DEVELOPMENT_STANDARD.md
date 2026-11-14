# OCR Automation — Development Standard

**Document ID:** OCRA-DEV-001  
**Version:** 2.0.0  
**Status:** Approved Architecture Baseline  
**Last Updated:** 2026-11-13

## 1. Purpose

This document is mandatory for all developers and AI coding agents working on OCR Automation. It establishes coding, architecture, security, testing, documentation, and change-management rules.

The project uses a Modular Feature Management Architecture. The objective is to add, update, disable, or remove business features without rewriting the application framework or unrelated features.

## 2. Source of Truth

Before writing or modifying code, inspect the current repository.

The current repository contents are the source of truth for implementation. These documents define the approved target architecture and standards. If the repository conflicts with these documents:
1. Do not silently rewrite the repository.
2. Identify the conflict and affected files.
3. Explain the proposed migration.
4. Obtain approval when the change is architectural or destructive.
5. Update documentation and changelog after approval.

Do not assume a proposed target folder already exists. Inspect before creating it.

## 3. Mandatory Pre-Change Checklist

Before implementing any task, the developer/AI must:
1. Read `ARCHITECTURE.md`.
2. Read `FOLDER_STRUCTURE.md`.
3. Read `MODULE_REGISTRY.md`.
4. Read `API_CONTRACTS.md`.
5. Read this document.
6. Inspect the actual repository tree.
7. Inspect the existing implementation and tests.
8. Search for an existing service, feature, component, model, or helper that already owns the requested responsibility.
9. Identify the exact files expected to change.
10. Identify configuration, database, contract, and migration impacts.

Do not begin coding based only on the user's short description when repository context is available.

## 4. Architecture Rules

### 4.1 Framework and Business Feature Separation
- Core is the always-present runtime framework.
- Core must not contain business-specific document extraction logic.
- Each business capability must be a separate Feature Module.
- Shared technical capabilities belong in Shared Services.
- Dashboard feature choices must be generated from Feature Registry data.
- Adding a feature must not require hardcoding it into the dashboard.

### 4.2 Single Responsibility and Ownership
Every module, class, service, and function must have one clear owner and responsibility.

Before creating a new implementation:
- Search for an existing owner.
- Reuse or extend the existing public interface when appropriate.
- Do not create duplicate OCR engines, PDF renderers, Excel writers, registries, authentication managers, or logging managers.
- If ownership is unclear, document the decision before implementation.

### 4.3 Loose Coupling
- Communicate through documented contracts.
- Do not import another feature's private implementation.
- Do not access another module's internal database tables directly.
- Avoid circular imports.
- Use dependency injection and typed events where appropriate.
- Do not expose implementation-specific library objects across service boundaries.

### 4.4 Backward Compatibility
- Do not break existing feature behavior without explicit approval.
- Preserve public contracts or introduce a versioned migration.
- Add regression tests for existing functionality affected by a change.
- Do not remove files or configuration keys merely because they appear unused; verify references first.

## 5. Feature Development Rules

Every new feature must:
1. Have a unique stable `feature_id`.
2. Include a valid `manifest.json`.
3. Declare version, publisher, entry point, Core/API compatibility, dependencies, permissions, configuration schema, and UI metadata.
4. Implement the approved Feature Contract.
5. Use Shared Services through public interfaces.
6. Keep document-specific detection, extraction, normalization, and business validation inside the feature.
7. Include feature-specific tests.
8. Document its configuration and user workflow.
9. Be registered through Feature Manager.
10. Appear dynamically in the GUI only after successful validation and enablement.

Runtime activation requirements:
- Implement the complete public `FeatureModule` contract: `initialize`, `get_descriptor`,
  `create_workspace`, `validate_configuration`, `execute`, and `shutdown`.
- Keep the runtime descriptor identical to the verified manifest metadata.
- Declare a package-contained `module:Class` entry point and `ui:Class` workspace target.
- Return a workspace instance of the declared workspace class; the Presentation adapter
  additionally requires a PySide6 `QWidget`.
- Treat in-process feature code as trusted code with application privileges; digest
  verification is not sandboxing.

Feature code must not:
- Modify another feature's files.
- Register itself by directly editing the registry database.
- Bypass authentication or authorization.
- Install arbitrary packages or execute unverified code.
- Create its own copy of a generic shared service.
- Write directly to the GUI main window or replace application navigation.

## 6. Shared Service Development Rules

Before adding a service:
- Confirm that at least two use cases need the capability, or document why centralization is justified now.
- Define a stable interface and typed models.
- Keep vendor/library-specific code inside an adapter.
- Provide a fake or in-memory implementation for tests where practical.
- Document error codes, resource limits, and compatibility.
- Avoid feature-specific business assumptions in generic services.

Changing a service adapter must not require feature changes when its public contract remains compatible.

## 7. Python Coding Standards

- Use the Python version pinned by project configuration.
- Use type hints for public functions and contracts.
- Prefer small, testable functions.
- Use `pathlib.Path` for filesystem paths.
- Use context managers for files, database connections, and temporary resources.
- Use structured exceptions and stable error codes.
- Use `logging` rather than `print` in production code.
- Avoid mutable global state and hidden singletons.
- Use dependency injection through the application composition root.
- Keep configuration explicit and validated.
- Avoid broad `except Exception` unless it is a top-level safety boundary that logs diagnostics and returns a controlled error.
- Never silently swallow errors.
- Avoid magic numbers; define named configuration values.
- Keep UI logic separate from business logic.
- Use background workers for long-running OCR/PDF/Excel work.

## 8. GUI Standards

The GUI is built with PySide6 unless an approved architecture decision changes it.

- Keep the GUI responsive.
- Do not execute OCR, PDF rendering, or large Excel operations on the GUI thread.
- Communicate worker progress through signals or the approved event mechanism.
- Render feature options dynamically from Feature Registry and authorization results.
- Do not hardcode feature dropdown entries.
- Display current file, processing stage, completed/total counts, warnings, and final result.
- Provide clear states for success, failed, skipped, and manual review.
- Keep feature-specific workspace components within the feature package or approved declarative UI schema.
- UI visibility must never replace backend authorization.

## 9. OCR and Document Processing Standards

- Keep source PDFs immutable.
- Validate file type, size, page count, and readability before processing.
- Configure DPI and preprocessing profiles rather than hardcoding them.
- Treat OCR confidence as an engine signal, not a guaranteed correctness probability.
- Validate critical extracted values using domain rules.
- Keep raw OCR output, normalized value, validation outcome, and confidence distinguishable.
- Record the engine and model version used for each job where practical.
- Use fallback detection when configured.
- Mark ambiguous values for review; do not silently invent or repair identifiers.
- Apply resource limits and cancellation checkpoints.

## 10. Excel Processing Standards

- Use configured mapping profiles; never hardcode worksheet/column positions in a business workflow.
- Validate workbook, worksheet, header row, data start row, source key, and target column before processing.
- Preserve identifiers as text where leading zeroes or formatting matter.
- Define normalization rules explicitly and test them.
- Detect duplicate source keys and duplicate extracted values.
- Define unmatched and overwrite policies.
- Do not overwrite the original workbook by default.
- Write to a temporary copy, verify output, and then promote to the destination.
- Preserve formulas, styles, worksheets, and workbook features to the extent supported by the selected adapter.
- Report unsupported workbook features and test representative customer templates.
- Never evaluate untrusted formulas or macros.

## 11. Security Standards

- Passwords must be hashed using Argon2id or an approved password hashing algorithm.
- Never store plaintext passwords, API keys, private signing keys, or license secrets in source code or ordinary configuration.
- Enforce RBAC/permission checks in application services.
- Use least privilege for filesystem access.
- Validate and normalize all user-supplied paths.
- Prevent path traversal and unsafe archive extraction.
- Verify package signature/digest against trusted information independent of the package.
- Do not load untrusted Python packages in-process.
- Treat local logs, databases, backups, and OCR output as potentially sensitive.
- Redact secrets and unnecessary personal/document data from logs.
- Use safe temporary file handling and cleanup.
- Provide secure backup and restore procedures.
- Keep license signing private keys outside the distributed application.

## 12. Database and Configuration Changes

Any database schema change must include:
1. Explanation of the change.
2. Migration script with an ordered version.
3. Upgrade behavior.
4. Rollback or recovery plan where feasible.
5. Tests for migration and data preservation.
6. Documentation update.

Configuration changes must:
- Update the relevant JSON schema or typed model.
- Define defaults.
- Define migration behavior for existing profiles.
- Reject invalid values with actionable messages.
- Avoid multiple sources of truth for the same setting.

## 13. Testing Requirements

Minimum testing for a change:
- Unit tests for changed logic.
- Contract tests for public interface changes.
- Integration tests for service interactions.
- Regression tests for affected existing features.
- Security tests for permissions, file paths, and package validation where relevant.
- Manual GUI test for visible interaction changes.

Use fixtures and fake services to avoid requiring real OCR engines or customer documents in every unit test.

Critical workflows must test:
- Valid input.
- Invalid/corrupt input.
- Empty input.
- Duplicate identifiers.
- Unmatched identifiers.
- Low-confidence extraction.
- Cancellation.
- Partial failure.
- Output write failure.
- Recovery after interruption.

## 14. Documentation and Registry Updates

When adding or changing a feature:
- Update Feature Registry documentation.
- Update the feature manifest and configuration schema.
- Update API contracts if public behavior changes.
- Update folder structure if new paths are introduced.
- Update architecture if a layer or dependency rule changes.
- Update `CHANGELOG.md`.
- Add or update user-facing instructions.

Do not leave stale examples or contradictory documentation.

## 15. Required AI/Developer Response Format

For each implementation task, provide:

### A. Repository Inspection
- Existing relevant files.
- Existing services/features reused.
- Any conflicts with standards.

### B. Change Plan
- Exact files to add, modify, or remove.
- Responsibility of each changed file.
- Dependencies and migration impacts.

### C. Implementation
- Complete code or a precise patch.
- No unexplained placeholders.
- No invented file paths.

### D. Tests
- Tests added/changed.
- Commands to run.
- Actual test results when executed.
- Any tests not run and why.

### E. Security and Compatibility Review
- Authorization and permission impacts.
- File and data handling risks.
- Backward compatibility.
- Regression risks.

### F. Documentation
- Documents and changelog updated.

### G. Known Limitations
- Remaining assumptions, unsupported formats, or operational risks.

## 16. Prohibited AI Behaviors

AI coding agents must not:
- Rewrite the whole project when the task concerns one feature.
- Change frameworks or architecture without approval.
- Create duplicate modules or services.
- Hardcode feature names into the dashboard.
- Bypass Feature Manager or Service Registry.
- Add dependencies without explaining purpose and offline packaging impact.
- Remove existing features or files without impact analysis and approval.
- Claim tests passed when they were not run.
- Claim offline support without confirming that all required models and dependencies are locally available.
- Claim security or OCR accuracy guarantees without evidence.
- Change database schemas without migrations.
- Modify unrelated files to make a task appear complete.

## 17. Definition of Done

A task is complete only when:
- The implementation follows the approved layer ownership.
- No duplicate responsibility has been introduced.
- Contracts and configuration schemas are valid.
- Authorization and package trust are respected.
- Tests are added and executed where possible.
- Existing affected features pass regression tests.
- Documentation and changelog are updated.
- The GUI remains responsive for long-running tasks.
- Errors and partial outcomes are visible and traceable.

## 18. Stage 5 Feature Manager implementation rules

- Keep Feature Manager orchestration in `app/feature_manager/`; keep SQLite SQL in the
  persistence repository and migration directories.
- Parse manifests before any feature entry point is considered for loading.
- Reject unknown manifest fields, unsupported schema versions, malformed dependencies,
  unsafe package-relative paths, and invalid entry-point paths.
- Compute package digests from package contents; never trust a digest declared only by a package.
- The trusted digest catalog must be provisioned independently of user-editable configuration.
- ZIP extraction must enforce path containment, reject symlinks, and enforce file/expanded-size limits.
- Do not import feature entry points as part of discovery or registration.
- Use the injected AuthorizationService for every mutation. A missing provider must deny access.
- Preserve package/data backups on uninstall and update; do not silently delete feature data.
- Do not update feature data schemas until an ordered migration and migration tests exist.
- Test package tampering, ZIP traversal, lifecycle transitions, dependency gates, authorization,
  active-job guards, audit persistence, and registry recovery.


## 19. Stage 6 Authentication and Authorization rules

- Keep authentication, authorization, password hashing, and session lifecycle in `app/security/`.
- Persist users, roles, permissions, login lockout state, and security audit through repositories;
  UI components must never issue SQL.
- Hash passwords with scrypt or another explicitly approved adaptive password-hashing algorithm.
  Never log, serialize, or expose plaintext passwords or password hashes.
- Use unique salts and constant-time digest comparison. Validate encoded KDF parameters before
  performing expensive verification to prevent malicious resource-exhaustion inputs.
- Do not ship a default Administrator username/password pair. Provision the initial Administrator
  through a first-run setup flow and ensure setup can only succeed once.
- Apply account lockout/rate limiting and session idle/absolute expiry. Do not reveal whether a
  username exists through ordinary login errors.
- Use permission IDs at application boundaries. Role names are policy/configuration data and must
  not be hardcoded into feature workflows.
- Re-check persisted user activity and permission assignments for each protected operation; do not
  rely only on permissions copied into a UI session at login time.
- Audit login success/failure, authorization denial, user creation, role changes, and account
  activation/deactivation without recording passwords, hashes, or sensitive document contents.
- Fail closed if the authorization provider or required persistence is unavailable.
- Protect the local database and backups with OS permissions; encryption-at-rest remains a deployment
  requirement to be validated against the selected threat model.


## 20. Stage 8.1 Feature Configuration Rules

- Core `ConfigManager` is application-global; feature profiles must be managed by the Feature Manager configuration service. Do not create a second global configuration manager.
- Feature configuration must be read from the manifest-declared schema within the installed package root. Reject path traversal and symbolic-link escapes.
- Persist profiles outside package source and separate them by installation/company/user/job scope.
- Require `feature.configure.<feature_id>` for configuration reads, writes, and resets; fail closed without authorization.
- Validate values before persistence and when loading existing profiles. Never silently accept unknown properties when the schema disallows them. The Stage 8.1 validator supports a documented JSON Schema subset and must reject unsupported keywords rather than silently ignore them.
- Use `x-config-version` for configuration profile versioning; do not conflate it with feature `data_schema_version`.
- Do not persist schema properties marked `writeOnly` or `x-secret` in ordinary JSON. A secure secret store must be designed separately.
- A version mismatch must block configuration use until a migration exists; do not silently rewrite stored profiles.
- Persist configuration changes through the repository contract, emit typed lifecycle events, and record an audit entry without logging configuration values.
- Every persistence schema change requires an ordered migration and data-preservation tests.


## Stage 8.2 — Feature Configuration UI Rules

- Feature configuration UI belongs to the Presentation Layer under Feature CMS.
- Build controls from the validated schema projection; never hardcode feature IDs or
  feature-specific property names.
- UI calls the public Feature Configuration Manager contract only; it must not access
  package files, SQLite repositories, or SQL directly.
- UI visibility checks are not authorization. The manager must re-authorize every
  schema read, profile read, save, and reset.
- Use typed widgets for scalar values and a JSON editor for structured values not
  represented by a dedicated widget. The manager remains the authoritative validator.
- Display safe, actionable errors and never expose stack traces or sensitive values.
- Secret-marked schema fields must remain blocked until a secure secret store exists.


## Stage 8.3 — Migration Development Rules

- Keep configuration `x-config-version` independent from feature `data_schema_version`.
- Provide every intermediate migration step; do not jump version numbers. Follow `docs/FEATURE_MIGRATION_GUIDE.md` for exact file formats and supported operations.
- Configuration migrations must use only the declarative operations documented in API contracts.
- Data migrations must be reviewed SQLite SQL under the owning feature package. Do not use `exec`, dynamic imports, shell commands, or arbitrary Python migration callbacks.
- Do not include transaction-control, connection-control, extension-loading, PRAGMA, or VACUUM statements in feature SQL migrations. The engine owns transaction boundaries.
- Preserve identifiers as text and preserve existing data unless a documented migration explicitly transforms it.
- Test successful migration, missing steps, invalid operations, SQL failure rollback, duplicate application, and backup retention.
- Do not claim package-and-data update atomicity until Stage 8.4 coordinates package, configuration, and feature-data rollback.


## 18. Health Check and Rollback Requirements

- A feature package checkpoint must be created only after verifying the installed digest
  against trust information independent of the package.
- Checkpoint journals must be written atomically and must not contain secrets.
- Health checks must be read-only and return typed, stable diagnostic results.
- Package integrity, manifest consistency, declared dependencies, configuration
  compatibility, and feature-data integrity must be checked before a changed feature is
  accepted.
- A failed health check must not be represented as a successful update.
- Rollback must verify the checkpoint package digest and manifest before restoring.
- Preserve the failed package for diagnostics when possible.
- Do not claim that package rollback reverses arbitrary feature-side effects or data
  migrations. Data restore requires a verified database backup and an explicit policy.
- Startup recovery must process only valid, prepared journals and must fail closed when
  checkpoint trust cannot be established.


## 19. Publisher Trust and Package Signing Requirements

- Production feature packages must be signed by an active, registered publisher key.
- Use Ed25519 for package signatures; do not invent custom cryptographic algorithms.
- Publisher private keys must remain outside the application and must never be committed,
  embedded in a package, or written to application logs.
- Store only raw Ed25519 public keys and trust metadata in the application.
- Bind signatures to publisher ID, feature ID, package version, and package digest.
- Exclude only the root-level `publisher_signature.json` envelope from the package digest.
- Reject package symlinks, malformed signature envelopes, inactive/revoked keys, revoked
  publishers, mismatched publisher names/IDs, and invalid signatures.
- Do not fall back to digest-only trust in production bootstrap.
- Key rotation must be explicit: provision and verify the new key, then revoke the old key.
- Publisher trust changes must be audited. Do not log private key material or signatures
  as user-facing diagnostic details.
- Test valid signatures, tampering, unknown publishers, key revocation, publisher
  revocation, wrong feature binding, and unauthorized trust-management actions.


## 18. Shared Services and Adapter Rules (Stage 9–10)

- Public interfaces must be Python `Protocol` definitions and remain independent of vendor libraries.
- Public request/response values must be immutable typed models where practical.
- Stable service IDs are `pdf.render`, `ocr.recognize`, `image.process`, `excel.workbook`, `validation.generic`, and `reporting.generate`.
- Register concrete implementations only through the existing `ServiceRegistry` at the composition root using `register_shared_services`; never create another registry.
- Features receive only `ServiceProvider` and must request a compatible service version.
- Keep engine/library imports inside adapters. Do not add a runtime dependency until its purpose, offline packaging footprint, license, and Windows compatibility are reviewed.
- Enforce resource ceilings and validate paths at the receiving adapter boundary.
- Keep OCR confidence engine-specific; do not claim calibrated probability.
- Preserve source PDFs and workbooks. Excel adapters must use temporary output and verification before promotion.
- Generic services must not contain feature-specific extraction or document classification rules.
- Provide fake implementations for contract and integration tests; unit tests must not require customer documents or local OCR models.
- Keep pypdfium2 imports inside `app/services/pdf/adapters/` and Pillow/OpenCV/NumPy imports inside `app/services/image/adapters/`. Review transitive/bundled license notices before release; the PDFium adapter is selected over PyMuPDF to avoid an AGPL/commercial dual-license dependency.
- PDF adapters must reject unsupported/encrypted/corrupt inputs with stable `ApplicationError` codes, enforce `ResourceLimits`, use zero-based internal page indexes, and never modify source PDFs.
- Image adapters must validate encoded input, format, byte size, and pixel count before processing; transformations must return new encoded bytes and never mutate source data.
- Adapter profiles and their accepted values must be explicit, validated, and covered by tests. Vendor exceptions must be translated to safe application errors.
- Third-party dependencies must be included in the pinned project lock and reviewed for Windows/Python compatibility and offline installer packaging.


## 21. Stage 12 Excel Adapter Requirements

- Keep openpyxl imports inside `app/services/excel/adapters/`; never expose its objects
  through `ExcelService`, models, Feature Modules, or Presentation.
- Support only explicitly validated workbook formats. Stage 12 supports `.xlsx` and
  `.xlsm`; do not silently treat `.xls`, `.xlsb`, or encrypted workbooks as supported.
- Treat identifiers as text by default. Preserve leading zeroes and test normalization
  profiles explicitly.
- Keep header resolution, key matching, duplicate handling, unmatched handling, and
  overwrite behavior driven by typed request/mapping models, not hardcoded feature rules.
- Never evaluate formulas or trust formulas/cell references extracted from documents.
  Formula-like incoming strings must be written as literal text.
- Never write to the source workbook. Stage output in the destination directory, verify
  the staged workbook, and atomically promote it.
- Report detectable workbook features with potential round-trip loss. Do not claim
  lossless preservation of pivot tables, charts, images, external links, macros, or
  digital signatures without format-specific tests.
- Include synthetic tests for corrupt/unsupported files, missing worksheets/headers,
  leading-zero keys, duplicate and unmatched policies, overwrite policies, formula
  preservation/literalization, source immutability, failed writes, and output verification.
- Add the exact openpyxl distribution and transitive dependencies to the supported
  Python 3.12 lockfile before release; verify its license notices and Windows wheel
  availability for offline packaging.


## Feature Workspace and Background Execution

- A feature workspace is created only through the manifest-declared workspace target and the approved `UIContext`.
- Feature UI code owns presentation and user input; it must not instantiate Shared Service adapters or access persistence directly.
- Long-running PDF, OCR, validation, and Excel work must execute outside the GUI thread. Use the application's job contracts and a worker mechanism with safe signal delivery to the UI.
- Keep worker objects alive until their threads have fully terminated. Feature shutdown/unload must not release injected services while a worker is still using them.
- Display only statuses and confidence values supported by the returned job results. Do not invent progress percentages or confidence values when the execution contract does not provide them.


## 14. Runtime and CI Reproducibility

- The supported development/test interpreter is Python 3.12.x, declared by `.python-version`
  and `project.requires-python`.
- Keep `uv.lock` synchronized with `pyproject.toml` and commit lockfile changes together
  with dependency metadata changes.
- Use `uv sync --locked --all-groups` for CI installation after lock validation.
- Windows CI must run the complete test suite with PySide6 installed; GUI/bootstrap tests
  must not be silently excluded.
- Headless GUI tests use `QT_QPA_PLATFORM=offscreen`; manual Windows visual inspection
  remains required for release-sensitive layout and native-dialog behavior.
- Record Python, PySide6/Qt, OCR engine, and dependency versions in validation reports.
- Do not mark a stage complete based only on Python compilation when its applicable tests
  could not be executed. Report unverified runtime requirements explicitly.
