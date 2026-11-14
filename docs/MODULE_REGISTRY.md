# OCR Automation — Feature Registry Standard

**Document ID:** OCRA-REG-001  
**Version:** 2.0.0  
**Status:** Approved Architecture Baseline  
**Last Updated:** 2026-11-13

## 1. Purpose and Terminology

This document replaces the former module registry concept with a **Feature Registry** standard.

A **Feature** is an independently managed business capability visible in the OCR Automation GUI, such as Tax Invoice Reader or Invoice Reader.

A **Service** is a reusable technical capability, such as OCR execution or Excel workbook access. Services are not selectable business features unless explicitly wrapped by a user-facing feature.

A **Package** is the distributable artifact containing a feature and its metadata.

The Feature Registry is the authoritative catalog of installed feature metadata and lifecycle state. It is not the source of truth for package code; package files and verified manifests remain the source for executable content.

## 2. Registry Responsibilities

Feature Registry must:
- Store a stable feature ID and metadata.
- Track installed version and lifecycle state.
- Track package location and integrity verification result.
- Track compatibility requirements and dependencies.
- Track enabled/disabled status.
- Track permissions and license entitlements.
- Track configuration schema/version.
- Expose authorized feature descriptors to the GUI.
- Record lifecycle changes and failures.

Feature Registry must not:
- Store executable source code as registry metadata.
- Treat UI visibility as permission enforcement.
- Allow arbitrary package paths or unverified entry points.
- Store secrets or plaintext passwords.
- Let a feature modify another feature's registry record directly.

## 3. Stable Feature Identity

`feature_id` is permanent once a feature is published.

Rules:
- Use lowercase `snake_case`.
- Must be unique within the application.
- Must not contain spaces or filesystem path separators.
- Do not reuse an ID for a different business capability.
- Renaming the display name does not change the ID.
- Breaking replacement of a feature requires a migration or a new ID with an explicit transition plan.

Examples:
- `tax_invoice`
- `invoice_reader`
- `receipt_reader`
- `purchase_order_reader`

## 4. Manifest Standard

Every installable feature package must include `manifest.json` at its package root. The
`entry_point` and `ui.workspace` targets use `module:Class` syntax and must resolve to
package-contained Python modules/classes when the runtime activates the feature.

Example:

```json
{
  "manifest_schema_version": "1.0",
  "feature_id": "tax_invoice",
  "display_name": "Pembacaan Faktur Pajak",
  "version": "1.0.0",
  "description": "Mendeteksi halaman faktur pajak dan mengekstraksi data terkait.",
  "publisher": "OCR Automation",
  "entry_point": "entry:TaxInvoiceFeature",
  "minimum_core_version": "0.1.3",
  "maximum_core_version": null,
  "api_contract_version": "2.15.0",
  "dependencies": {
    "features": [],
    "services": [
      {"id": "pdf.render", "version": "1.0.0"},
      {"id": "ocr.recognize", "version": "1.0.0"},
      {"id": "image.process", "version": "1.0.0"},
      {"id": "excel.workbook", "version": "1.0.0"},
      {"id": "validation.generic", "version": "1.0.0"}
    ]
  },
  "permissions": [
    "filesystem.read_input",
    "filesystem.write_output",
    "pdf.read",
    "ocr.execute",
    "excel.read",
    "excel.write"
  ],
  "configuration_schema": "config_schema.json",
  "ui": {
    "navigation_label": "Pembacaan Faktur Pajak",
    "icon": "file-search",
    "workspace": "ui:TaxInvoiceWorkspace"
  },
  "license_entitlement": "feature.tax_invoice",
  "data_schema_version": 1
}
```

The example is illustrative. The implementation must validate manifests against a maintained JSON Schema. Unknown critical fields, invalid paths, unsupported contract versions, and malformed dependencies must cause rejection.

## 5. Required and Optional Metadata

| Field | Required | Description |
|---|---:|---|
| `manifest_schema_version` | Yes | Manifest schema version |
| `feature_id` | Yes | Stable unique identifier |
| `display_name` | Yes | Localized/user-facing name |
| `version` | Yes | Semantic version |
| `description` | Yes | Feature purpose |
| `publisher` | Yes | Package publisher |
| `entry_point` | Yes | Approved feature entry point |
| `minimum_core_version` | Yes | Minimum compatible Core |
| `api_contract_version` | Yes | Feature contract version |
| `dependencies` | Yes | Required features/services |
| `permissions` | Yes | Requested capabilities |
| `configuration_schema` | Yes | Feature configuration schema |
| `ui` | Yes | Dashboard/workspace metadata |
| `license_entitlement` | No | Required license entitlement |
| `data_schema_version` | Yes | Feature-owned persisted data version |
| `maximum_core_version` | No | Optional upper compatibility bound |

All package paths must be normalized and verified to remain inside the package root. Reject path traversal, absolute paths, symlinks escaping the package root, and unexpected executable files.

## 6. Registry Record

The persistent registry record should include:

```json
{
  "feature_id": "tax_invoice",
  "installed_version": "1.0.0",
  "package_path": "features/tax_invoice",
  "package_digest": "sha256:<digest>",
  "publisher_key_id": "publisher-key-01",
  "signature_status": "verified",
  "manifest_schema_version": "1.0",
  "api_contract_version": "2.3.0",
  "state": "enabled",
  "enabled": true,
  "installed_at": "2026-11-05T00:00:00Z",
  "updated_at": "2026-11-05T00:00:00Z",
  "last_error_code": null,
  "data_schema_version": 1
}
```

Timestamps and digest values above are examples only. The registry should store normalized values and use UTC internally.

## 7. Lifecycle States

| State | Meaning | Dashboard |
|---|---|---|
| `discovered` | Package found, not yet validated | No |
| `validating` | Manifest/package checks in progress | No |
| `registered` | Valid package registered, disabled by default | No |
| `enabled` | Feature available and executable | Yes, subject to access |
| `disabled` | Installed but unavailable for execution | No |
| `update_pending` | Update staged, not yet activated | Existing stable version only |
| `uninstall_pending` | Removal requested and safety checks running | No new jobs |
| `error` | Load, dependency, or migration failure | No |
| `quarantined` | Integrity or trust failure | No |
| `uninstalled` | Package removed from installed catalog | No |

Transitions must be validated by Feature Manager. Direct status edits in a database or UI are prohibited.

## 8. Feature Lifecycle Operations

### Register
Validate the manifest, package layout, dependencies, compatibility, signature/digest, permissions, and configuration schema. Registration does not automatically enable the feature.

### Install
Stage the package in a temporary location, verify it, scan paths, validate metadata, run approved migrations, then atomically move it into the installed feature directory and register it.

### Enable
Check package integrity, compatibility, dependencies, license, configuration, and permission declarations. Only then transition to `enabled`.

### Disable
Prevent new jobs, allow or safely cancel active jobs according to policy, persist the disabled state, and remove the feature from the dashboard. Do not delete feature data.

### Update
Stage a new version separately. Verify it before activation. Run migrations transactionally where possible. Keep the previous package/version available for rollback until health checks pass.

### Uninstall
Require administrator authorization and confirmation. Block while jobs are active. Check dependents and data-retention policy. Back up or retain feature-owned data according to policy. Remove package files only after a successful state transition.

## 9. Dashboard Discovery Rules

The dashboard's feature list is derived from:
1. Registry state is `enabled`.
2. Package integrity is currently acceptable.
3. Dependencies are satisfied.
4. License entitlement is valid if required.
5. User has the required feature permission.

Feature ordering and labels may be configurable, but display configuration must not alter the stable `feature_id`.

## 10. Feature Configuration

Each feature owns its configuration schema and defaults.

Configuration rules:
- Validate configuration against the feature's schema.
- Store configuration separately from package source.
- Scope configuration by installation, company/tenant, user, or job as appropriate.
- Never store secrets in plain JSON.
- Version configuration independently using the schema `x-config-version` (default `1`) and provide migrations when it changes.
- Support installation, company, user, and job configuration scopes.
- Reject secret-marked fields in ordinary JSON profiles; use a dedicated secure secret store when implemented.
- Invalid configuration must prevent execution and provide an actionable error.

For Tax Invoice Reader, possible settings include:
- Search region defaulting to the upper 25% of a page.
- DPI.
- OCR engine and language/model.
- Minimum OCR confidence.
- Fallback scan strategy.
- Tax invoice and invoice number extraction rules.
- Excel mapping profile.
- Duplicate and unmatched policies.

## 11. Dependency Rules

- Feature dependencies must be declared as `{ "id": "feature_id", "version": "1.x" }`, version-constrained, and acyclic.
- Prefer Shared Services over dependencies between business features.
- A feature must not import another feature's private modules.
- Disabling or uninstalling a required dependency must be blocked or require a controlled dependent-feature operation.
- Missing or incompatible services must prevent activation with a clear diagnostic.

## 12. Versioning and Compatibility

Use Semantic Versioning:
- MAJOR: breaking feature contract or data behavior.
- MINOR: backward-compatible feature capability.
- PATCH: backward-compatible fixes.

Core API contract versions and manifest schema versions are separate from feature versions.

Compatibility must be checked before package activation. Do not assume that a higher version number means compatibility.

## 13. Package Trust and Security

- Only trusted, verified packages may be installed.
- Verify publisher signature where package signing is implemented; otherwise use a controlled trusted-package digest allowlist for development.
- Do not accept a digest supplied only by the package itself as proof of integrity.
- Store trust anchors outside writable feature package directories.
- Ordinary users cannot install, update, or uninstall packages.
- Python modules execute with the application's process privileges; in-process loading is not a sandbox.
- Untrusted third-party extensions must not be loaded in-process. Use process isolation and a restricted IPC contract if external plugins are ever supported.
- Quarantine packages that fail verification.

## 14. Registry Change Audit

Record:
- Actor/user ID.
- Timestamp.
- Feature ID.
- Operation.
- Previous and resulting state/version.
- Package digest.
- Result and error code.
- Approval/confirmation reference where applicable.

Do not record secrets or full document contents.

## 15. Acceptance Criteria

The registry implementation is acceptable when:
- A valid feature can be discovered and registered without dashboard code changes.
- An enabled feature appears dynamically for an authorized user.
- A disabled feature is not executable even if a user manually invokes its route/action.
- An invalid or tampered package is rejected and quarantined.
- An update can roll back after failed validation/health checks.
- Uninstall is blocked while a job is active.
- Feature state transitions and package operations are auditable.

## 16. Stage 5 implementation mapping

| Registry responsibility | Implementation |
|---|---|
| Manifest parsing/schema validation | `app/feature_manager/manifest_loader.py` and `schemas/manifest.schema.json` |
| Package discovery | `app/feature_manager/discovery.py` |
| Package integrity | `app/feature_manager/package_verifier.py` |
| Package archive installation | `app/feature_manager/installer.py` |
| Lifecycle policy | `app/feature_manager/lifecycle_manager.py` |
| Application Feature Manager | `app/feature_manager/manager.py` |
| Public models/contracts | `app/feature_manager/models.py`, `contracts.py` |
| Persistent registry/audit | `app/persistence/repositories/feature_registry_repository.py` |
| Initial schema migration | `app/persistence/migrations/0001_feature_registry.sql` |
| Dashboard/CMS projection | `app/ui/view_models/feature_catalog.py`, `feature_management.py` |

The current bootstrap uses persisted RBAC authorization after first-run Administrator setup and
sign-in. Feature lifecycle mutations still require the corresponding permission at the application
boundary. The trusted-digest allowlist remains empty until protected publisher trust-anchor
provisioning is implemented. Do not add trusted hashes to user-editable config.


## 17. Stage 6 Permission Integration

Feature manifests continue to declare permission identifiers, not role names. The Core RBAC
provider resolves user permissions from role assignments and supports exact permission IDs, the
global `*` grant, and namespace wildcard grants such as `feature.view.*` and
`feature.configure.*`. Feature Manager filters the catalog using `feature.view.<feature_id>` and
re-checks the relevant configure/install/update/uninstall permission for each lifecycle mutation.

The initial system roles are Administrator, Operator, and Viewer. These are seeded by the Core
authentication migration, not by feature packages. Administrator is provisioned only through the
first-run setup flow; no default credentials are distributed. Features must never check role names
directly.


## Stage 7 Runtime Activation

A registry record in `enabled` state is necessary but not sufficient for loading. Runtime
activation performs a fresh package-integrity, dependency, license, and user-permission
check. The Feature Manager runtime loads the declared entry point only after those checks
pass. A loaded feature is initialized once per live runtime instance and is shut down on
disable, update, uninstall, or application shutdown. Runtime loading is in-process and
therefore restricted to trusted packages; Python packages are not sandboxed.


## 18. Stage 8.1 Feature Configuration Implementation

| Responsibility | Implementation |
|---|---|
| Configuration models and scopes | `app/feature_manager/models.py` |
| Public configuration contracts | `app/feature_manager/contracts.py` |
| Configuration orchestration, authorization, schema validation, defaults, events | `app/feature_manager/configuration_manager.py` |
| SQLite configuration persistence | `app/persistence/repositories/feature_configuration_repository.py` |
| Configuration profile schema | `app/persistence/migrations/0003_feature_configuration.sql` |
| Unit tests | `tests/unit/feature_manager/test_configuration_manager.py`, `test_configuration_repository.py` |

Feature configuration profiles are independent of feature package files. The registry
remains the authoritative source for installed package metadata; configuration profiles
are persisted in their own table and cannot be edited directly by feature code.


## Stage 8.2 — Configuration Management UI

Feature configuration editing is a Core/Presentation management capability, not a
business Feature Module and not a registry entry. The Feature CMS renders controls
from the selected installed feature's validated `config_schema.json` projection
provided by `FeatureConfigurationManager`. It must not hardcode business feature IDs
or configuration property names. Secret-marked properties remain unavailable until
a dedicated secure secret store is implemented.


## Stage 8.3 — Feature Migration Assets

Migration files are package-owned metadata/scripts, not independent Features or Services.
They must be located only in the package's `migrations/configuration/` or
`migrations/data/` directories and use sequential `NNNN_to_NNNN` names. Configuration
migrations are declarative JSON with the four documented operations. Data migrations are
SQLite SQL scripts and execute only after package integrity/trust verification against the external trusted digest allowlist. A feature
package must not access another feature's data store. The application-owned migration
engine records feature data migration history and keeps configuration profile versions
separate from `data_schema_version`.


## 16. Health and Recovery Metadata

Health reports are transient diagnostic projections; they do not replace the Feature
Registry lifecycle record. Rollback checkpoints are stored outside feature package
directories under the protected application backup root. Each checkpoint contains a
verified package copy and an atomic `journal.json` describing the prior package digest,
manifest, lifecycle state, and recovery status.

The Feature Registry remains authoritative for installed metadata and lifecycle state.
A rollback must restore the verified prior manifest and update the registry through the
repository contract; direct UI/database edits are prohibited.


## 17. Publisher Trust Registry

Publisher Trust Registry is separate from Feature Registry because publisher identity
and trust lifecycle are not feature lifecycle metadata.

It stores:
- Stable publisher ID and display name.
- Publisher status (`active` or `revoked`).
- One or more Ed25519 public keys, each with a fingerprint-derived key ID.
- Per-key status (`active` or `revoked`).
- Creation/revocation timestamps.
- Trust-management audit events.

The registry never stores publisher private keys. Feature Registry continues to store
the package digest and verification status; it does not become the source of publisher
trust. Publisher revocation blocks subsequent package verification.


## 19. Stage 10 Shared Service Adapter Inventory

Shared Services are technical capabilities and are not Feature Registry entries. The initial concrete adapters are:

| Service ID | Public contract | Adapter | Runtime dependencies |
|---|---|---|---|
| `pdf.render` | `PDFService` | `app/services/pdf/adapters/pypdfium2_adapter.py` (`PdfiumAdapter`) | pypdfium2/PDFium |
| `image.process` | `ImageService` | `app/services/image/adapters/opencv_adapter.py` (`OpenCVImageAdapter`) | Pillow, OpenCV headless, NumPy |

Both adapters are registered by the application composition root. Their lifecycle is owned by the application process, not by individual features. The adapters are not installed, enabled, disabled, or uninstalled through Feature Manager.


## 20. Stage 12 Shared Service Adapter Inventory

| Service ID | Public contract | Adapter | Runtime dependency |
|---|---|---|---|
| `excel.workbook` | `ExcelService` | `app/services/excel/adapters/openpyxl_adapter.py` (`OpenpyxlExcelAdapter`) | openpyxl |

`OpenpyxlExcelAdapter` is owned by Shared Services and is registered by the existing
application composition-root helper. It is not a Feature Registry entry and has no
independent enable/disable lifecycle. The public contract remains engine-neutral; feature
packages must not import openpyxl or the adapter implementation.

Supported workbook formats are `.xlsx` and `.xlsm`. Unsupported or partially preserved
workbook features are reported through descriptor/write warnings where detectable.


## 21. Stage 13.3 Tax Invoice Feature Implementation

| Responsibility | Owner | Public dependencies |
|---|---|---|
| Marker canonicalization and page-candidate decisions | `features/tax_invoice/detector.py` | Tax Invoice models, `NormalizedRegion` |
| PDF metadata, embedded text, and page rendering | `features/tax_invoice/extractor.py` orchestration | `PDFService` (`pdf.render`) |
| Scanned-page OCR and raw identifier capture | `features/tax_invoice/extractor.py` orchestration | `OCRService` (`ocr.recognize`) |
| Feature lifecycle and per-file job result adaptation | `features/tax_invoice/entry.py` | Feature Runtime, `JobRequest`, `JobResult`, Service Provider |
| Feature configuration validation | Existing `FeatureConfigurationManagerService` | `config_schema.json` |
| Detection/extraction tests | `features/tax_invoice/tests/test_detection_extraction.py` | Fake PDF/OCR services |

The Tax Invoice feature does not instantiate PDFium, Tesseract, OpenCV, or Excel adapters.
The current detection/extraction scope is two identifiers only. Normalization, domain
validation, Excel mapping/output, and the GUI workspace remain assigned to Stages 13.4–13.6.


## 22. Stage 13.5 Tax Invoice Excel Mapping and Output

The Tax Invoice feature now consumes the declared `excel.workbook` Shared Service for
configured workbook inspection, record reading, mapping, writing, and verification. Excel
configuration is optional so extraction-only jobs remain backward compatible.

Write eligibility is deliberately strict: only `success` results enter Excel write records.
`review` (display label **Need Review**), `failed`, and `skipped` results are excluded. A
missing normalized key/value downgrades an otherwise successful result to `review`. The
source workbook is immutable; `JobRequest.output_path` is the separate output destination.


## 23. Stage 13.6 Tax Invoice GUI Workspace

| Responsibility | Owner | Contract / dependency |
|---|---|---|
| Feature workspace construction | `features/tax_invoice/entry.py` | `UIContext`, manifest workspace target |
| PDF selection, processing controls, optional Excel mapping, results presentation | `features/tax_invoice/ui.py` | PySide6 Widgets, `JobRequest`, `JobResult` |
| Background execution | `features/tax_invoice/ui.py` (`_TaxInvoiceJobWorker`) | Qt `QThread`; delegates to `TaxInvoiceFeature.execute` |
| OCR/PDF/Excel work | Existing Shared Services through `TaxInvoiceFeature` | `pdf.render`, `ocr.recognize`, `excel.workbook` |

The workspace owns presentation only. It does not construct adapters or access persistence.
The three user-facing statuses are **Success**, **Need Review**, and **Failed**; internal
`review` remains unchanged. Only internal `success` results remain eligible for Excel writes.
The GUI uses an indeterminate progress indicator because the current feature execution
contract does not expose per-file progress callbacks.
