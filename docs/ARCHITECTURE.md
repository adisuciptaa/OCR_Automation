# OCR Automation — Architecture

**Document ID:** OCRA-ARCH-001  
**Version:** 2.0.0  
**Status:** Approved Architecture Baseline  
**Last Updated:** 2026-11-13

## 1. Purpose

This document defines the target architecture for OCR Automation, an offline-first Windows desktop application built with Python. The application processes scanned PDF documents, extracts structured information, matches extracted values against existing Excel workbooks, and writes validated results into configurable spreadsheet templates.

The architecture must support the addition, removal, enablement, disablement, configuration, and versioning of business features through a GUI-based Feature Management interface.

## 2. Architectural Decision

OCR Automation adopts a **Modular Feature Management Architecture**.

The application is composed of:

1. **Application Framework (Core):** the always-present runtime foundation responsible for application lifecycle, authentication, authorization, configuration, service registration, feature discovery, UI composition, logging, and persistence coordination.
2. **Feature Manager:** the framework subsystem responsible for registering, validating, installing, enabling, disabling, updating, and uninstalling feature packages.
3. **Feature Modules:** independently packaged business capabilities such as Tax Invoice Reader, Invoice Reader, Receipt Reader, and Purchase Order Reader.
4. **Shared Services:** reusable technical capabilities such as PDF rendering, OCR execution, image preprocessing, Excel access, validation, and reporting.
5. **Infrastructure Adapters:** concrete implementations for local filesystem, SQLite, cryptography, operating-system integration, and other external dependencies.

The Core is not a business-feature container. Business functionality must live in feature modules. The Core remains installed because it provides the runtime required to discover and execute modules.

## 3. Architectural Goals

- Add a new business feature without rewriting existing features or the main dashboard.
- Remove or disable a feature without damaging the application framework or other features.
- Render the available feature list dynamically from the Feature Registry and user permissions.
- Keep reusable technical logic in Shared Services rather than duplicating it inside features.
- Operate without internet access during normal use.
- Support standalone installations and a future LAN/shared deployment mode without coupling business features to a specific deployment mode.
- Preserve source documents and original Excel workbooks.
- Make processing traceable, recoverable, testable, and auditable.
- Support controlled commercial distribution and offline license validation.

## 4. High-Level Architecture

```text
┌──────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                    │
│ Login | Dashboard | Feature Workspace | Feature CMS      │
│ Settings | User Management | History | Reports           │
└───────────────────────────┬──────────────────────────────┘
                            │ UI actions / view models
┌───────────────────────────▼──────────────────────────────┐
│                APPLICATION FRAMEWORK (CORE)               │
│ Application Lifecycle | AuthN | AuthZ | Config            │
│ Feature Manager | Service Registry | Event Bus | Logging │
│ Navigation | Job Orchestration | Audit | License         │
└───────────────┬───────────────────────────┬──────────────┘
                │ feature contracts        │ service contracts
┌───────────────▼──────────────┐  ┌─────────▼────────────────┐
│       FEATURE MODULES        │  │      SHARED SERVICES     │
│ Tax Invoice Reader           │  │ PDF Service              │
│ Invoice Reader               │  │ OCR Service              │
│ Receipt Reader               │  │ Image Processing         │
│ Purchase Order Reader        │  │ Excel Service            │
│ Future business modules      │  │ Validation / Reporting   │
└──────────────────────────────┘  └─────────┬────────────────┘
                                            │ adapters
┌───────────────────────────────────────────▼──────────────┐
│                    INFRASTRUCTURE                         │
│ SQLite | Local Filesystem | OCR Models | OS / Crypto     │
└──────────────────────────────────────────────────────────┘
```

## 5. Layer Responsibilities

### 5.1 Presentation Layer

Responsible only for displaying information and collecting user input.

Responsibilities:
- Render the main dashboard and dynamic feature dropdown/catalog.
- Render feature-specific UI supplied through approved UI contracts.
- Display job progress, current file, counters, warnings, and final reports.
- Display Feature CMS screens to authorized administrators.
- Perform client-side input validation for usability.

Restrictions:
- Must not contain OCR, PDF, Excel, database, or authorization business logic.
- Must not decide access rights based only on hidden buttons or menu visibility.
- Must not import internal implementation classes from feature packages.

### 5.2 Application Framework (Core)

The Core is a small, stable runtime framework, not a monolithic business application.

Responsibilities:
- Bootstrap and shut down the application.
- Manage authentication, authorization, user sessions, and audit events.
- Discover and validate feature manifests.
- Maintain the Feature Registry and feature lifecycle state.
- Resolve approved Shared Services through the Service Registry.
- Compose navigation and feature workspaces dynamically.
- Coordinate background jobs and application events.
- Load configuration and license state.
- Provide stable contracts and error-handling conventions.

The Core must not contain document-specific extraction rules, such as tax invoice number patterns or receipt-specific field mapping.

### 5.3 Feature Manager

Feature Manager is responsible for:
- Discovering installed feature packages from approved locations.
- Keeping editable repository sources separate from installed packages in the OS-managed application-data directory (`features/installed/<feature_id>`).
- Validating manifest schema, package integrity, compatibility, dependencies, and permissions.
- Registering feature metadata.
- Enabling and disabling features.
- Installing, updating, and uninstalling packages through controlled operations.
- Preventing removal while a feature is executing or has an incomplete migration.
- Maintaining lifecycle history and rollback information.
- Running package, dependency, configuration, and feature-data health checks before accepting a change.
- Exposing only enabled and authorized features to the dashboard.

Feature Manager must not execute arbitrary code from untrusted packages. Package trust and integrity must be verified before loading.

### 5.4 Feature Modules

A feature module represents one business capability and owns its document-specific workflow.

Examples:
- `tax_invoice`: detect Indonesian tax invoice pages and extract tax invoice and related invoice numbers.
- `invoice_reader`: extract invoice fields.
- `receipt_reader`: extract receipt fields.
- `purchase_order_reader`: extract purchase order fields.

A feature may contain:
- Manifest and configuration schema.
- Detector and extractor.
- Feature-specific validator and normalizer.
- Workflow orchestration.
- Feature-specific UI declarations or UI factory, subject to the approved UI contract.
- Feature-specific tests and migration scripts.

A feature must call Shared Services through documented interfaces. It must not duplicate PDF rendering, OCR engine lifecycle, generic Excel workbook handling, authentication, or logging.

### 5.5 Shared Services

Shared Services expose reusable technical capabilities through stable interfaces.

Initial services:
- `pdf_service`: inspect PDF metadata, page count, render pages, extract embedded text when available.
- `ocr_service`: execute OCR using a selected local engine and return text, geometry, and engine confidence.
- `image_service`: crop, deskew, denoise, threshold, and normalize images.
- `excel_service`: inspect workbooks, read configured cells/columns, preserve workbook structure, and write output safely.
- `validation_service`: reusable format and consistency checks.
- `report_service`: produce processing summaries and machine-readable reports.

Service implementations may change without requiring feature modules to change, provided their public contracts remain compatible.

Stage 10 provides concrete adapters: pypdfium2/PDFium for PDF inspection/rendering/embedded text and Pillow/OpenCV for image transformations. Stage 11 adds a Tesseract-backed OCR adapter through the existing engine-neutral `OCRService` contract. All adapters are composed at application bootstrap through the existing Service Registry; vendor-specific objects remain inside adapter implementations. Excel remains a future stage.

### 5.6 Infrastructure

Infrastructure contains concrete technical adapters:
- SQLite repository implementation.
- Local filesystem access.
- Local OCR engine and model files.
- Cryptographic signature verification.
- Windows-specific integration.
- Secure secret and key handling.

## 6. Feature Discovery and Dashboard Behavior

The dashboard must not hardcode business features.

At startup:
1. Feature Manager scans approved feature package locations.
2. Each package manifest is parsed and schema-validated.
3. Package integrity and compatibility are checked.
4. Feature dependencies and permissions are checked.
5. Valid features are registered.
6. The user's permissions and license entitlements are applied.
7. The dashboard receives a list of available features.
8. Selecting a feature opens its registered workspace.

A feature appears in the user's dropdown/catalog only when:
- It is installed and registered.
- Its status is `enabled`.
- Its Core and service dependencies are satisfied.
- Its license entitlement is valid, when licensing applies.
- The current user has the required permission.

UI visibility is not an authorization boundary. Every execution request must be authorized again by the application layer.

## 7. Feature Lifecycle

Supported states:

`discovered → validated → registered → enabled`

Alternative and terminal transitions:
- `registered → disabled`
- `enabled → disabled`
- `disabled → enabled`
- `disabled → uninstall_pending → uninstalled`
- `enabled → update_pending → validated_new_version → enabled`
- Any validation or load failure may transition to `error` or `quarantined`.

Uninstall must be blocked when:
- A feature job is running.
- A database migration is incomplete.
- The package is required by another installed feature.
- An administrator has not confirmed the operation.

Disabling a feature must not delete its data. Uninstall must follow an explicit data-retention policy and must not silently delete processing history or user output.

## 8. Feature Execution Workflow

A typical document-processing job follows this sequence:

1. User selects a feature from the dashboard.
2. UI loads the feature's configuration and input controls.
3. User selects a PDF input folder and Excel template/workbook.
4. The feature validates inputs and creates a job request.
5. Application authorization and license checks run.
6. Job Orchestrator creates a job record and background task.
7. Feature workflow calls PDF, OCR, image, validation, and Excel services.
8. Progress events are emitted with job ID, file, stage, and counters.
9. Extracted data is matched to the configured Excel source key.
10. Results are validated and written to a temporary output workbook.
11. The output is verified and atomically promoted to its final destination where supported.
12. Job summary, per-file outcomes, warnings, and audit events are persisted.

The UI must remain responsive during processing. Long-running work must not execute on the GUI thread.

## 9. OCR Quality and Detection Principles

OCR configuration must be explicit and feature-scoped where behavior differs.

Common settings may include:
- Rendering DPI.
- OCR engine and local model/language packs.
- Image preprocessing profile.
- Minimum OCR confidence threshold.
- Retry/fallback strategy.
- Maximum page count or processing limits.

Confidence is an engine-provided quality signal, not a guaranteed probability that a value is correct. Critical extracted values must also pass format, checksum, cross-field, or business validation where applicable.

For the initial Tax Invoice feature:
- Search the upper portion of each rendered page for `FAKTUR PAJAK`.
- The initial search region may default to the top 25% of the page.
- Use configurable preprocessing and OCR.
- Validate the candidate page using additional tax-invoice characteristics.
- Extract tax invoice number and related invoice number using feature-specific rules.
- If detection fails, use a configured fallback such as a larger region or full-page scan.
- Ambiguous or low-confidence results must be marked for manual review rather than silently accepted.

## 10. Excel Mapping Principles

Excel mapping belongs to feature configuration and uses the shared Excel Service.

A mapping profile should support:
- Workbook and worksheet selection.
- Header row and data start row.
- Source key column or named table column.
- Target output column.
- Optional field mappings.
- Data type and normalization rules.
- Duplicate handling.
- Unmatched handling.
- Existing-value overwrite policy.
- Output file strategy.

Invoice identifiers must be treated as strings where leading zeroes or formatting are significant. Matching must use explicit normalization rules and must not remove meaningful characters.

The original workbook must remain untouched by default. Write to a new output file or a controlled temporary copy. Preserve formulas, styles, worksheets, and workbook features as far as the chosen library supports them. Unsupported workbook features must be disclosed and tested.

## 11. Data, Persistence, and Audit

SQLite is the initial local persistence option. Repository interfaces must isolate application logic from the database implementation.

Persist at minimum:
- Users, roles, and permissions.
- Feature registry metadata and lifecycle state.
- Feature configuration profiles.
- Job records and per-file results.
- Audit events.
- License metadata.
- Schema migration version.

Do not store passwords in plaintext. Use Argon2id or another approved password hashing implementation. Protect local database files and backups with operating-system permissions and an appropriate encryption strategy where the threat model requires it.

## 12. Security Model

- Apply least privilege.
- Enforce authorization in application services, not only in the UI.
- Use password hashing, session expiry, account lockout/rate limiting, and secure recovery procedures.
- Validate all file paths and prevent path traversal.
- Restrict file operations to configured/authorized locations.
- Verify feature package signatures or hashes against a trusted publisher policy.
- Use an allowlist of trusted feature packages.
- Do not permit arbitrary plugin installation by ordinary users.
- Do not treat Python plugins as a sandbox. A plugin loaded in-process can generally access the process privileges.
- Use process isolation for untrusted or high-risk extensions if such extensions are ever supported.
- Avoid logging sensitive document contents, credentials, or unnecessary personal data.
- Maintain tamper-evident or access-controlled audit records.
- Validate offline license signatures locally; never embed private signing keys in the client application.

## 13. Deployment Modes

### Standalone
- Application, SQLite database, OCR models, and runtime directories reside on one workstation.
- This is the initial deployment target.

### LAN / Shared Deployment (Future)
- Multiple clients may connect to a central service or shared data layer.
- Do not implement multi-user concurrent writes to a shared SQLite file over a network share as the production architecture.
- Introduce a server-side service and suitable database when concurrent multi-client operation is required.
- Keep feature contracts independent of deployment mode.

## 14. Architectural Quality Attributes

| Attribute | Required approach |
|---|---|
| Modularity | Independent feature packages and stable contracts |
| Extensibility | Dynamic Feature Registry and Service Registry |
| Maintainability | Single responsibility, explicit ownership, tests |
| Reliability | Temporary output, atomic promotion, recovery |
| Security | Least privilege, package verification, RBAC |
| Offline operation | Local engines, models, license validation |
| Performance | Background workers, bounded concurrency, configurable DPI |
| Traceability | Job IDs, per-file results, audit logs |
| Compatibility | Semantic versioning and contract compatibility |

## 15. Architecture Decision Rules

Any proposed architecture change must:
1. State the problem being solved.
2. Identify affected layers and modules.
3. Explain alternatives and trade-offs.
4. Update the relevant architecture and contract documents.
5. Include migration and compatibility plans.
6. Include tests proving existing features remain functional.

No feature may bypass Feature Manager or directly modify another feature's internal files.

## 16. Stage 5 Feature Management implementation

The Stage 5 implementation introduces the Feature Manager backend under `app/feature_manager/`
without moving the existing Core or Presentation modules. It is composed through
`app/bootstrap.py` and persists registry metadata in the OS-managed application data directory.

Implemented responsibilities:
- Strict manifest parsing against the maintained `manifest.schema.json` schema.
- Discovery from the approved `features/` directory only.
- Deterministic SHA-256 package digest verification against an externally provisioned allowlist.
- SQLite registry metadata and lifecycle audit records.
- Validated register, enable, disable, update, and uninstall operations.
- Safe ZIP staging with path traversal, symbolic-link, compressed-size, file-count, and expanded-size checks; rejected security-invalid archives are preserved in quarantine where size permits.
- Version-constrained, acyclic feature dependencies and compatible shared-service dependency gates.
- Dependency, compatibility, license, active-job, and authorization gates.
- Dynamic dashboard catalog projection and a read-only Feature CMS registry view.

Security integration status after Stage 6:
- Local Authentication and RBAC are implemented in the Core Security subsystem. First-run setup
  provisions an initial Administrator, and production startup requires sign-in before showing the
  application workspace.
- Feature Manager receives the persisted RBAC AuthorizationService and continues to enforce
  permission checks at its application boundary. The deny-all adapter remains available for tests
  and fail-closed operation when no provider is configured.
- The production bootstrap deliberately retains an empty trusted-digest allowlist. Trust anchors
  must be provisioned by a protected installer/publisher mechanism, not editable application
  configuration. Package installation remains unavailable until that trust provisioning exists.
- Stage 7 now provides controlled loading of verified feature packages and lazy workspace
  activation. Package verification is not a sandbox; only trusted packages may be loaded.
- Stage 8.3 now provides declarative configuration-profile migrations and transactional SQL migrations for isolated per-feature SQLite data stores. Migration packages must pass the external trusted digest allowlist.
- Automatic package updates that change `data_schema_version` remain blocked until Stage 8.4 coordinates package, configuration, and data rollback with health checks. Failed update staging restores the previous package; post-update health checks and coordinated rollback remain pending.
- Stages 8.1, 8.2, and 8.3 provide feature configuration management, schema-driven configuration UI, and migration execution. Publisher trust management remains pending.

These boundaries are intentional and must not be represented as completed security or
business-processing capabilities.


## 17. Stage 6 Authentication and Authorization

The Core Security subsystem is implemented under `app/security/`. It provides credential
verification, local session lifecycle, permission-based RBAC, first-run Administrator setup,
user administration, and security audit persistence. User and role data are stored through the
SQLite persistence adapter and migration `0002_authentication.sql`.

Security boundaries:
- UI navigation and page visibility are usability controls only. Protected application services
  independently check permissions for every operation.
- Feature code consumes permission identifiers; it must not branch on role names.
- Passwords use salted scrypt hashes from the Python standard library. No additional runtime
  dependency is introduced for password hashing.
- Five failed login attempts trigger a 15-minute account lockout. Sessions expire after 30 minutes
  idle time or 12 hours absolute lifetime.
- The initial Administrator is created interactively; no default credentials are shipped.
- Password recovery, MFA, remote identity providers, and LAN/shared sessions remain out of scope.


## Stage 7 — Feature Runtime Loading & Workspace Activation

The Core composition root creates one `FeatureRuntimeManager` and injects it into the
Presentation workspace adapter. The runtime remains a Feature Manager concern; the
Dashboard and main window know only the `FeatureWorkspaceFactory` presentation contract.

Activation flow:
1. User selects a feature already present in the authorized dynamic catalog.
2. The runtime requests a fresh enabled feature record from Feature Manager.
3. Feature Manager re-checks RBAC permission, enabled lifecycle state, package digest,
   declared dependencies, and license entitlement.
4. Runtime imports the verified entry point under a unique package namespace, checks
   descriptor parity with the manifest, and initializes it with `FeatureContext`.
5. Runtime supplies a service provider restricted to manifest-declared dependencies,
   then calls `create_workspace(UIContext)`; the Presentation adapter requires a
   PySide6 `QWidget` before returning it to the main window.
6. Disable, update, uninstall, and application shutdown events release the feature via
   `shutdown()` and remove its private module namespace.

Feature Python code executes in-process with the application's OS privileges. Package
digest checks establish integrity, not sandbox isolation; package trust provisioning is
still a prerequisite for production package activation. Long-running `execute` work is
not dispatched by the GUI and remains the responsibility of the future Job Orchestrator.


## Stage 8.1 — Feature Configuration Manager

Feature configuration is managed by `FeatureConfigurationManagerService` within the
Feature Manager layer. It is distinct from Core `ConfigManager`, which continues to own
application-global settings only. The service reads the schema declared by the verified
feature manifest, validates profile values, applies schema defaults, and persists profiles
through a dedicated SQLite repository.

Configuration profiles are scoped to installation, company, user, or job. The installation
scope has the fixed key `default`; all other scopes require an explicit scope key. Reads,
writes, and resets are protected by `feature.configure.<feature_id>`. Profiles are stored
outside feature package directories and are versioned independently through the schema's
`x-config-version` (default `1`). A version mismatch is blocked until the Stage 8.3 migration
engine explicitly migrates the profile against the target schema. Secret-marked schema fields are rejected rather than written to plain
JSON.


## Stage 8.2 — Feature Configuration Presentation

Feature configuration is presented inside Feature CMS through a schema-driven dialog.
The Presentation Layer consumes only the public `FeatureConfigurationManager` contract
and an immutable validated schema projection. It does not inspect feature package
files or access configuration persistence directly. Every read, save, and reset is
re-authorized by Feature Manager; UI permission checks only control action visibility.


## Stage 8.3 — Feature Data Migration Engine

`FeatureDataMigrationEngine` is owned by `app/feature_manager/migration_engine.py` and
is registered through the existing Service Registry as `feature.migrations`. It handles
two independent version streams: configuration profile `x-config-version` and feature
`data_schema_version`. These versions must never be conflated.

Configuration migrations use sequential declarative JSON files under
`features/<feature_id>/migrations/configuration/`, named
`NNNN_to_NNNN.json`. Supported operations are `rename_field`, `remove_field`,
`set_default`, and `map_value`. All stored profiles for a feature are transformed and validated against the target schema,
then committed through one repository transaction. A missing step or invalid operation blocks
the migration without changing any profile.

Feature-owned SQLite data migrations use sequential SQL files under
`features/<feature_id>/migrations/data/`, named `NNNN_to_NNNN.sql`. Each feature has an
isolated database under the application data directory. SQL runs in a single SQLite
transaction per requested version range; transaction-control, connection-control,
PRAGMA, extension-loading, and VACUUM statements are rejected. A pre-migration database
backup is retained after success. SQL migration files are executable data changes and
may only be accepted from packages verified against the externally provisioned trusted digest allowlist.

The engine is exposed to application services, not to Presentation or business features
for direct repository access. Stage 8.4 will coordinate migration completion with
post-update health checks and package/data rollback. Until that coordinator is available,
Feature Manager's automatic package update continues to reject `data_schema_version`
changes rather than claiming an atomic package-and-data update.


## 16. Feature Health Check and Recovery

Feature Health Check Manager performs read-only diagnostics for the installed package,
manifest, declared dependencies, configuration profiles, and feature-owned SQLite data.
It returns a typed health report and does not silently change lifecycle state.

Feature Rollback Coordinator creates a verified package checkpoint with a durable,
atomically written recovery journal. A rollback restores the verified package and prior
registry metadata. Interrupted prepared checkpoints can be detected by `recover_pending`.

Package rollback is not a general transaction across arbitrary plugin side effects.
Feature data restoration must use a separately verified database backup. A release/update
workflow must not report success until its post-change health report is healthy; an
unhealthy report requires the coordinator to retain the prior checkpoint and stop
promotion. Untrusted packages remain blocked by Publisher Trust Management.


## 17. Publisher Trust Management

Publisher Trust Manager owns trusted publisher identities, active/revoked Ed25519 public
keys, key rotation, publisher revocation, and signature verification. Its SQLite
repository stores public keys and an append-only trust audit trail. Publisher private
keys remain outside the application and are used by the publisher-side signing utility.

A signed feature package carries a root-level `publisher_signature.json` envelope. The
signature binds publisher ID, feature ID, semantic version, and the SHA-256 digest of
the package. The digest excludes only the signature envelope itself; all other regular
files, including the manifest, are covered. Symlinks are rejected.

Production bootstrap composes Publisher Trust Manager before PackageVerifier and injects
the trust-aware verifier into installation, update, runtime, health-check, and rollback
flows. No production fallback to the previous digest-only allowlist is permitted.
Unknown or revoked publishers, inactive keys, missing signatures, and altered packages
are rejected. Revocation applies to subsequent verification; forced unloading of already
running feature instances is a future lifecycle enhancement.


## Stage 12 — Excel Engine Adapter

The Excel Shared Service now has a concrete `OpenpyxlExcelAdapter` implementation behind
the existing `ExcelService` protocol. Its composition-root registration uses the existing
Service Registry under `excel.workbook`; no new registry, Feature Manager entry, or
business-feature dependency is introduced.

The adapter owns all openpyxl imports and converts library objects into public immutable
models. It supports `.xlsx` and `.xlsm`, workbook inspection, configured record reads,
mapping-based key matching, and controlled output writes. It preserves source workbooks
by writing to a temporary copy, verifying the staged result, and atomically promoting it
to the requested destination. Formula values are not evaluated; extracted formula-like
strings are stored as literal text.

The adapter reports detectable round-trip risks for workbook features such as pivot tables,
charts, images, external links, and VBA signatures. openpyxl does not guarantee lossless
round-tripping of every advanced Excel feature. Representative customer workbooks must
be tested before production use.
