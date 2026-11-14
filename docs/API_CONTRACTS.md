# OCR Automation — API and Layer Contracts

**Document ID:** OCRA-API-001  
**Version:** 2.15.0  
**Status:** Approved Architecture Baseline  
**Last Updated:** 2026-11-14

## 1. Purpose

This document defines in-process contracts between the Presentation Layer, Application Framework, Feature Manager, Feature Modules, Shared Services, and Infrastructure.

The term API includes Python interfaces, typed request/response models, events, and persistence repository contracts. These are internal desktop application contracts; they are not automatically network APIs.

## 2. Contract Principles

- Depend on interfaces/protocols, not concrete implementations.
- Use typed request and response models.
- Keep business rules in feature workflows.
- Keep generic technical behavior in Shared Services.
- Use stable error codes and structured diagnostics.
- Avoid circular dependencies.
- Do not expose database models or engine-specific objects across layer boundaries.
- Use dependency injection through the application composition root.
- Version contracts explicitly.
- Keep UI communication asynchronous for long-running operations.

## 3. Dependency Direction

```text
Presentation → Application Contracts
Application/Core → Feature Contracts + Service Interfaces
Feature Modules → Public Service Interfaces
Service Adapters → Service Interfaces + Infrastructure
Infrastructure → OS / Libraries / Persistence
```

Forbidden:
- UI → concrete OCR engine.
- UI → feature internal extractor.
- Shared Service → business feature.
- Feature A → Feature B internal Python module.
- Feature → database connection or SQL implementation.
- Feature → direct manipulation of another feature's configuration or files.

## 4. Common Data Models

Use immutable dataclasses or validated Pydantic models where appropriate. Avoid passing untyped dictionaries across public contracts unless the schema is explicitly documented.

### 4.1 JobRequest

```python
@dataclass(frozen=True)
class JobRequest:
    job_id: str
    feature_id: str
    input_paths: tuple[str, ...]
    output_path: str
    configuration: Mapping[str, object]
    requested_by: str
    correlation_id: str
```

### 4.2 JobProgress

```python
@dataclass(frozen=True)
class JobProgress:
    job_id: str
    stage: str
    current_file: str | None
    completed_files: int
    total_files: int
    message_code: str
    message: str
```

### 4.3 FileResult

```python
@dataclass(frozen=True)
class FileResult:
    source_path: str
    status: Literal["success", "failed", "review", "skipped"]
    extracted_fields: Mapping[str, object]
    confidence: Mapping[str, float]
    warnings: tuple[str, ...]
    error_code: str | None
```

### 4.4 JobResult

```python
@dataclass(frozen=True)
class JobResult:
    job_id: str
    status: Literal["completed", "completed_with_warnings", "failed", "cancelled"]
    total_files: int
    successful_files: int
    failed_files: int
    review_files: int
    results: tuple[FileResult, ...]
    output_path: str | None
```

Paths crossing a boundary must be validated and normalized by the receiving service. Avoid exposing secrets or raw document contents in progress events.

## 5. Feature Contract

Every feature entry point must implement the approved feature interface.

Illustrative Python protocol:

```python
from typing import Protocol, Mapping, Any

class FeatureContext(Protocol):
    services: "ServiceProvider"
    event_bus: "EventBus"
    logger: "Logger"
    feature_id: str

class FeatureModule(Protocol):
    def initialize(self, context: FeatureContext) -> None: ...
    def get_descriptor(self) -> "FeatureDescriptor": ...
    def create_workspace(self, context: "UIContext") -> object: ...
    def validate_configuration(self, config: object) -> object: ...
    def execute(self, request: object) -> object: ...
    def shutdown(self) -> None: ...
```

Implementation notes:
- Long-running `execute` work must be invoked by the Job Orchestrator in a worker, not on the GUI thread.
- The feature must not create its own global application, database, or OCR engine singleton.
- `initialize` must be safe to call once per loaded feature instance.
- `shutdown` must release feature-owned resources.
- UI creation must follow the supported PySide6 UI extension strategy; feature code must not replace the main application window.
- If a feature does not need a custom workspace, it may use a declarative form/table schema supported by the UI framework.

## 5.1 Feature Runtime and Workspace Contracts (2.3.0)

The Feature Runtime is an Application Framework / Feature Manager capability. It loads
only a package that is currently enabled, integrity-verified, dependency-compatible,
licensed, and authorized for the requesting user.

Public runtime contexts:

```python
@dataclass(frozen=True, slots=True)
class FeatureContext:
    services: ServiceProvider
    event_bus: EventBus
    logger: Logger
    feature_id: str

@dataclass(frozen=True, slots=True)
class UIContext:
    parent: object
    actor_id: str
    feature_id: str
```

The feature entry point must implement `initialize(context)`, `get_descriptor()`,
`create_workspace(context)`, `validate_configuration(config)`, `execute(request)`, and
`shutdown()`. The runtime imports and verifies both the manifest-declared `module:Class`
entry point and `ui:Class` workspace declaration under the package namespace. It verifies
that the returned descriptor exactly matches the verified manifest metadata and that the
workspace instance matches the declared workspace class. The Presentation adapter
additionally requires that it is a `QWidget`.

Runtime rules:
- Re-check enabled state, package digest, dependencies, license, and
  `feature.view.<feature_id>` permission on every activation request.
- Expose only Shared Services declared in the feature manifest's service dependency list;
  undeclared service lookups fail with `FEATURE_SERVICE_NOT_DECLARED`.
- Load the manifest-declared `module:Class` under a unique package namespace so
  package-relative imports work without adding the feature directory to global
  `sys.path`.
- Initialize one live instance per feature ID; repeated activation reuses it while
  the verified package digest remains unchanged.
- Call `shutdown()` and remove namespaced modules when disabled, updated, uninstalled,
  or when the application shuts down.
- Map unexpected initialization failures to `FEATURE_LOAD_FAILED`; keep stack traces
  in protected logs, not ordinary user messages.
- Feature code runs in-process with application privileges. Digest verification is a
  package-integrity control, not a Python sandbox. Only trusted publisher packages may
  be loaded.
- `execute(request)` is a feature contract entry point; long-running execution remains
  the Job Orchestrator's responsibility and must not run on the GUI thread.

The application service exposes `get_enabled_feature(feature_id, user_id)` for runtime
activation. It returns a record only after current lifecycle, authorization, integrity,
dependency, and license checks pass.

## 6. Feature Descriptor

```python
@dataclass(frozen=True)
class FeatureDescriptor:
    feature_id: str
    display_name: str
    description: str
    version: str
    icon: str
    required_permissions: tuple[str, ...]
    license_entitlement: str | None
```

Descriptor values must agree with the verified manifest. Runtime code must not override stable package identity or requested permissions.

### 6.1 Presentation Feature Catalog Projection

The Presentation Layer consumes a display-only projection of the authorized feature catalog.
It must not read registry storage or package manifests directly. The application composition
layer adapts the current authenticated session and `FeatureManager.list_available(user_id)`
result into this presentation contract.

Illustrative Python contract:

```python
@dataclass(frozen=True)
class FeatureSummary:
    feature_id: str
    display_name: str
    description: str
    version: str
    icon: str = "document"

class FeatureCatalogProvider(Protocol):
    def list_available(self) -> tuple[FeatureSummary, ...]: ...
```

Rules:
- The provider is session-scoped and returns only features already filtered for enabled state,
  package integrity, dependencies, license entitlement, and the current user's permissions.
- This projection is for presentation only; it is not an authorization decision. The application
  boundary must re-authorize every execution or lifecycle action.
- The UI must not hardcode business feature IDs or import feature package internals.
- An unavailable provider yields an explicit empty state; the UI must not invent feature entries.

A presentation workspace adapter may resolve a validated feature module and delegate its
`create_workspace(UIContext)` method. It must return a widget owned by the supplied workspace
container and must never replace the main application window or navigation. The adapter belongs
to the application composition layer; feature code must not mutate the global window.

## 7. Service Provider Contract

Features request approved services by stable service ID and compatible version.

Illustrative API:

```python
class ServiceProvider(Protocol):
    def get(self, service_id: str, version: str | None = None) -> object: ...
```

The provider must:
- Resolve only registered services.
- Enforce compatibility.
- Fail with a structured `ServiceUnavailableError` when unavailable.
- Avoid returning internal service registry mutation methods to feature code.

## 8. PDF Service Contract

```python
class PDFService(Protocol):
    def inspect(self, path: str) -> "PDFMetadata": ...
    def render_page(
        self,
        path: str,
        page_index: int,
        dpi: int,
        region: "NormalizedRegion | None" = None
    ) -> "RenderedPage": ...
    def extract_embedded_text(self, path: str, page_index: int) -> str: ...
```

Rules:
- Page indexes are zero-based internally.
- User-facing page numbers are one-based.
- Validate file existence, file type, page limits, and path permissions.
- Respect configured memory and rendering limits.
- Do not silently overwrite source PDFs.

## 9. OCR Service Contract

```python
class OCRService(Protocol):
    def recognize(
        self,
        image: "ImageInput",
        options: "OCROptions"
    ) -> "OCRResult": ...
```

`OCRResult` should include:
- Recognized text.
- Word/line bounding boxes when supported.
- Engine confidence values when supported.
- Engine ID and engine version.
- Language/model identifiers.
- Warnings and preprocessing metadata.

Confidence must be documented as engine-specific. Do not represent it as a calibrated probability unless a calibration process has been validated.

The OCR service must not decide whether a document is a tax invoice or invoice. That is feature-specific business logic.

## 10. Image Service Contract

```python
class ImageService(Protocol):
    def crop(self, image: "ImageInput", region: "NormalizedRegion") -> "ImageInput": ...
    def deskew(self, image: "ImageInput") -> "ImageInput": ...
    def denoise(self, image: "ImageInput", profile: str) -> "ImageInput": ...
    def enhance_contrast(self, image: "ImageInput", profile: str) -> "ImageInput": ...
```

Image transformations must be reproducible where practical and must not mutate the original source artifact.

## 11. Excel Service Contract

```python
class ExcelService(Protocol):
    def inspect_workbook(self, path: str) -> "WorkbookDescriptor": ...
    def read_records(self, request: "ExcelReadRequest") -> "ExcelReadResult": ...
    def write_records(self, request: "ExcelWriteRequest") -> "ExcelWriteResult": ...
    def verify_output(self, path: str) -> "WorkbookVerificationResult": ...
```

Excel mapping model:

```python
@dataclass(frozen=True)
class ExcelMapping:
    worksheet: str
    header_row: int | None
    data_start_row: int
    source_key_column: str
    target_column: str
    key_type: Literal["text", "number"]
    normalization_profile: str
    duplicate_policy: Literal["reject", "review", "first", "all"]
    unmatched_policy: Literal["report", "skip", "fail"]
    overwrite_policy: Literal["empty_only", "overwrite", "review"]
```

The concrete engine-neutral request/response models are:

```python
@dataclass(frozen=True)
class ExcelReadRequest:
    path: str
    worksheet: str
    header_row: int | None
    data_start_row: int
    columns: tuple[str, ...]

@dataclass(frozen=True)
class ExcelRecord:
    row_number: int
    values: tuple[tuple[str, object], ...]

@dataclass(frozen=True)
class ExcelWriteRequest:
    source_path: str
    destination_path: str
    worksheet: str
    records: tuple[ExcelRecord, ...]
    overwrite_policy: Literal["empty_only", "overwrite", "review"] = "empty_only"
    mapping: ExcelMapping | None = None
```

`ExcelReadRequest.columns` and `ExcelMapping` column values accept an exact header label when
`header_row` is configured; otherwise they must be Excel column letters. The mapping-based
write path expects each input `ExcelRecord.values` to contain the configured
`source_key_column` and `target_column` keys. `row_number` remains required by the shared
record model; mapping-based writes use the configured workbook key rather than trusting an
input row coordinate.

Supported normalization profiles are `exact`, `trim`, `casefold`, `trim_casefold`, `remove_whitespace`, and `remove_whitespace_casefold`. The latter profiles remove all whitespace characters before matching; the casefold variant also performs Unicode case folding.
`text` is the default key type and preserves leading zeroes; `number` uses decimal
normalization. Duplicate policy applies to duplicate workbook keys and duplicate incoming
keys: `reject` fails, `review` skips ambiguous keys with a warning, `first` selects the
first encountered key/record, and `all` broadcasts one incoming value to all duplicate workbook rows, or pairs duplicate
incoming values with duplicate workbook rows in worksheet order when the counts match;
mismatched duplicate counts fail as ambiguous. Unmatched `fail` aborts the write; `report`
and `skip` do not write unmatched records, with `report` adding a warning.

Rules:
- Treat identifiers as text by default.
- Preserve leading zeroes.
- Never overwrite the original workbook by default.
- Write to a temporary copy, verify, then promote to final output.
- Preserve formulas, styles, worksheets, and workbook features as far as the adapter supports.
- Report unsupported features before processing.
- Define behavior for duplicate keys, duplicate extracted documents, unmatched keys, and existing target values.
- Never use a formula or cell coordinate supplied by an untrusted document as executable content.
- The Stage 12 openpyxl adapter supports `.xlsx` and `.xlsm`; it does not support `.xls`, `.xlsb`, or encrypted workbooks.
- Formulas are loaded as formula text, never evaluated. Extracted strings beginning with `=` are stored as literal text.
- `.xlsm` files are opened with VBA preservation enabled; macro signatures may be invalidated. Pivot tables, charts, images, external links, and other advanced workbook features may have round-trip limitations and must be surfaced as warnings.
- Output must be written beside the requested destination as a temporary copy, verified, and promoted with an atomic replace. Source and destination paths must differ.

## 12. Feature Manager Contract

```python
class FeatureManager(Protocol):
    def install_archive(self, archive_path: str, actor_id: str) -> "FeatureRecord": ...
    def discover(self) -> tuple["PackageCandidate", ...]: ...
    def validate(self, candidate: "PackageCandidate") -> "PackageValidationResult": ...
    def register(self, candidate: "PackageCandidate") -> "FeatureRecord": ...
    def enable(self, feature_id: str, actor_id: str) -> "FeatureRecord": ...
    def disable(self, feature_id: str, actor_id: str) -> "FeatureRecord": ...
    def update(self, feature_id: str, package_path: str, actor_id: str) -> "FeatureRecord": ...
    def uninstall(self, feature_id: str, actor_id: str) -> "FeatureRecord": ...
    def list_available(self, user_id: str) -> tuple["FeatureDescriptor", ...]: ...
    def get_enabled_feature(self, feature_id: str, user_id: str) -> "FeatureRecord": ...
```

Every mutation must enforce authorization, validate lifecycle state, and emit an audit event.

## 13. Authentication and Authorization Contracts

Authentication verifies identity. Authorization decides whether an authenticated identity may perform an action.

Use permission identifiers rather than hardcoding role names inside features.

Example permissions:
- `job.execute`
- `job.cancel`
- `job.view_own`
- `job.view_all`
- `feature.view.tax_invoice`
- `feature.registry.view`
- `feature.configure.tax_invoice`
- `feature.install`
- `feature.update`
- `feature.uninstall`
- `user.manage`
- `audit.view`

Illustrative contract:

```python
class AuthorizationService(Protocol):
    def require(self, actor_id: str, permission: str, resource: object | None = None) -> None: ...
    def is_allowed(self, actor_id: str, permission: str, resource: object | None = None) -> bool: ...
```

Authorization must be checked at the application boundary for every action. UI visibility is not sufficient.

### 13.1 Authentication and Session Contracts

Authentication is provided by the Core Security subsystem. The initial desktop implementation
uses a local SQLite user store and process-local sessions. Authentication and authorization
remain separate services.

Illustrative public models and contracts:

```python
@dataclass(frozen=True)
class UserIdentity:
    user_id: str
    username: str
    display_name: str
    is_active: bool
    roles: tuple[str, ...]
    permissions: tuple[str, ...]

class AuthenticationService(Protocol):
    def setup_initial_administrator(self, username: str, display_name: str, password: str) -> UserIdentity: ...
    def authenticate(self, username: str, password: str) -> UserIdentity: ...

class SessionService(Protocol):
    def has_active_user_session(self, user_id: str) -> bool: ...
    def create(self, identity: UserIdentity) -> UserSession: ...
    def get(self, session_id: str) -> UserSession | None: ...
    def revoke(self, session_id: str) -> None: ...
```

The Presentation Layer depends on these protocols rather than importing the concrete authentication
manager. User administration operations are exposed through a separate `UserAdministrationService`
contract and remain protected by `user.manage`.

Implementation rules:
- First-run setup creates exactly one initial Administrator; there is no built-in default password.
- Passwords are stored only as salted, adaptive password hashes. The current adapter uses
  standard-library scrypt with encoded parameters and constant-time digest comparison.
- Password policy requires at least 12 characters and limits input to 128 characters.
- Failed login attempts are persisted; five consecutive failures trigger a 15-minute lockout.
- Inactive and locked accounts cannot authenticate. Error messages do not disclose whether a username exists.
- Sessions are process-local, expire after 30 minutes of inactivity, and have a 12-hour absolute lifetime. The desktop Sign out action revokes the session as the application exits.
- User and role mutations require `user.manage`; authorization is re-evaluated against persisted
  assignments for each protected operation.
- The Administrator role receives the global `*` permission. Operator and Viewer are least-privilege
  starter roles; deployments may refine their assignments through approved administration tooling.
- Security audit records contain actor, action, target, outcome, stable error code, timestamp, and
  limited structured metadata. Passwords, hashes, and document contents must never be audited.
- Password reset/recovery, MFA, remote identity providers, and shared/LAN sessions are out of scope
  for this local Stage 6 implementation.

### 13.2 Persistence Contracts

The authentication repository owns user credentials, role assignments, permission assignments,
login lockout counters, and security audit persistence. Presentation components must not issue SQL.
The schema is introduced by ordered migration `0002_authentication.sql` in the same application
SQLite database used by the Feature Registry.

## 14. Event Contract

Use typed events for progress and lifecycle notifications.

Examples:
- `feature.registered`
- `feature.enabled`
- `feature.disabled`
- `feature.updated`
- `feature.uninstalled`
- `job.started`
- `job.progress`
- `job.file_completed`
- `job.completed`
- `job.failed`
- `job.cancelled`

Events should include:
- Event ID.
- Event name/version.
- Timestamp.
- Correlation ID.
- Actor ID where applicable.
- Job or feature ID.
- Structured payload.

Do not include full OCR text or sensitive document fields unless explicitly required and access-controlled.

## 15. Error Contract

Use stable machine-readable error codes plus safe human-readable messages.

Examples:
- `FEATURE_MANIFEST_INVALID`
- `FEATURE_PACKAGE_INVALID`
- `FEATURE_PACKAGE_PATH_INVALID`
- `FEATURE_ENTRY_POINT_INVALID`
- `FEATURE_DEPENDENCY_INCOMPATIBLE`
- `FEATURE_DEPENDENCY_CYCLE`
- `FEATURE_LIFECYCLE_INVALID`
- `FEATURE_BUSY`
- `FEATURE_HAS_DEPENDENTS`
- `FEATURE_LICENSE_INVALID`
- `FEATURE_MIGRATION_REQUIRED`
- `FEATURE_ROLLBACK_FAILED`
- `FEATURE_UNINSTALL_FAILED`
- `FEATURE_SIGNATURE_INVALID`
- `FEATURE_CORE_INCOMPATIBLE`
- `FEATURE_DEPENDENCY_MISSING`
- `FEATURE_PERMISSION_DENIED`
- `FEATURE_LOAD_FAILED`
- `FEATURE_CONTRACT_INVALID`
- `FEATURE_DESCRIPTOR_MISMATCH`
- `FEATURE_WORKSPACE_INVALID`
- `FEATURE_NOT_AVAILABLE`
- `FEATURE_SERVICE_NOT_DECLARED`
- `AUTH_INVALID_CREDENTIALS`
- `AUTH_ACCOUNT_LOCKED`
- `AUTH_PASSWORD_POLICY`
- `AUTH_PERMISSION_DENIED`
- `AUTH_USERNAME_EXISTS`
- `AUTH_USERNAME_INVALID`
- `AUTH_ROLE_REQUIRED`
- `AUTH_ROLE_INVALID`
- `AUTH_INITIAL_SETUP_COMPLETE`
- `AUTH_SELF_DEACTIVATION_DENIED`
- `AUTH_LAST_ADMIN_REQUIRED`
- `OCR_ENGINE_UNAVAILABLE`
- `OCR_LOW_CONFIDENCE`
- `PDF_PATH_INVALID`
- `PDF_FILE_NOT_FOUND`
- `PDF_INVALID_FILE_TYPE`
- `PDF_FILE_SIZE_LIMIT`
- `PDF_CORRUPT`
- `PDF_ENCRYPTED`
- `PDF_INVALID_PAGE_INDEX`
- `PDF_PAGE_INDEX_OUT_OF_RANGE`
- `PDF_PAGE_LIMIT_EXCEEDED`
- `PDF_INVALID_DPI`
- `PDF_RENDER_PIXEL_LIMIT`
- `IMAGE_INPUT_INVALID`
- `IMAGE_FORMAT_UNSUPPORTED`
- `IMAGE_MEDIA_TYPE_MISMATCH`
- `IMAGE_DECODE_FAILED`
- `IMAGE_FILE_SIZE_LIMIT`
- `IMAGE_PIXEL_LIMIT_EXCEEDED`
- `IMAGE_PROFILE_INVALID`
- `EXCEL_MAPPING_INVALID`
- `EXCEL_PATH_INVALID`
- `EXCEL_FILE_NOT_FOUND`
- `EXCEL_FILE_SIZE_LIMIT`
- `EXCEL_FORMAT_UNSUPPORTED`
- `EXCEL_WORKBOOK_CORRUPT`
- `EXCEL_EXPANDED_SIZE_LIMIT`
- `EXCEL_WORKBOOK_ENCRYPTED`
- `EXCEL_WORKBOOK_COMPLEXITY_LIMIT`
- `EXCEL_REQUEST_INVALID`
- `EXCEL_WORKSHEET_NOT_FOUND`
- `EXCEL_HEADER_DUPLICATE`
- `EXCEL_COLUMN_NOT_FOUND`
- `EXCEL_KEY_NOT_FOUND`
- `EXCEL_DUPLICATE_KEY`
- `EXCEL_SOURCE_OVERWRITE_BLOCKED`
- `EXCEL_DESTINATION_INVALID`
- `EXCEL_DESTINATION_FORMAT_MISMATCH`
- `EXCEL_SOURCE_OVERWRITE_BLOCKED`
- `EXCEL_NO_ROWS_WRITTEN`
- `EXCEL_VALUE_UNSUPPORTED`
- `EXCEL_WRITE_FAILED`
- `EXCEL_NO_ROWS_WRITTEN`
- `EXCEL_OUTPUT_VERIFICATION_FAILED`
- `JOB_CANCELLED`

Errors must not expose stack traces, credentials, internal paths, or sensitive document content to ordinary users. Full diagnostic details may be stored in protected logs.

## 16. Background Job Contract

- Jobs must have unique IDs and correlation IDs.
- GUI communicates with workers through signals/events.
- Workers must support cancellation at safe checkpoints.
- Progress must report current file and stage.
- Job state transitions must be validated.
- A failed file must not silently fail the entire batch unless the selected policy requires fail-fast behavior.
- Final job summary must distinguish success, failed, review, and skipped files.

## 17. Contract Versioning

- Maintain an explicit `api_contract_version`.
- Backward-compatible additions may be MINOR changes.
- Breaking interface or behavior changes require a MAJOR version.
- Deprecate before removal where practical.
- Contract tests must run against every installed feature.
- Core must reject incompatible feature packages before loading/execution.

## 18. Contract Acceptance Criteria

- A sample feature can run using only public contracts.
- A fake OCR/PDF/Excel service can be injected for tests.
- No feature imports another feature's internal modules.
- No UI component calls an OCR engine directly.
- Unauthorized operations are rejected even when invoked outside the GUI.
- Progress and errors are typed and correlated to a job.
- Contract compatibility is checked before feature activation.

## 19. Stage 5 Feature Manager implementation details

The concrete application service is `FeatureManagerService` in `app/feature_manager/manager.py`.
Its public operations are:

```python
class FeatureManager(Protocol):
    def install_archive(self, archive_path: str, actor_id: str) -> FeatureRecord: ...
    def discover(self) -> tuple[PackageCandidate, ...]: ...
    def validate(self, candidate: PackageCandidate) -> PackageValidationResult: ...
    def register(self, candidate: PackageCandidate, actor_id: str) -> FeatureRecord: ...
    def enable(self, feature_id: str, actor_id: str) -> FeatureRecord: ...
    def disable(self, feature_id: str, actor_id: str) -> FeatureRecord: ...
    def update(self, feature_id: str, package_path: str, actor_id: str) -> FeatureRecord: ...
    def uninstall(self, feature_id: str, actor_id: str) -> FeatureRecord: ...
    def list_available(self, user_id: str) -> tuple[FeatureDescriptor, ...]: ...
```

Implementation contracts:
- `AuthorizationService` is injected; every mutation calls `require` at the application boundary.
- Feature and service dependencies are version-constrained; service and feature versions accept exact versions and `MAJOR.x` / `MAJOR.MINOR.x` selectors.
- Manifest schema version `1.0` is validated using the maintained `app/feature_manager/schemas/manifest.schema.json`.
- API contract compatibility is checked by major version; Core minimum/maximum versions use semantic version components.
- Package digests are deterministic SHA-256 hashes over sorted relative paths and file bytes.
- `SQLiteFeatureRegistryRepository` owns registry and lifecycle audit persistence; UI does not issue SQL.
- Feature descriptors are projected only for enabled, verified, dependency-satisfied, licensed, authorized records.
- Feature package paths must resolve within the approved feature root. Package entry-point modules must also remain within the package root.
- `install_archive` stages and verifies a ZIP before atomic placement in the feature root. Archive limits are 128 MiB compressed, 2,000 entries, and 256 MiB expanded size. Security-invalid archives are copied to the configured quarantine directory when within the quarantine size limit.
- Update is blocked when active jobs exist or a data schema migration is required. The previous package is retained under the configured backup root.
- Uninstall is blocked for active jobs and enabled dependents; package files are retained in backup storage rather than silently deleted.

The desktop Feature Management UI delegates publisher registration to `PublisherTrustManager.register_publisher`, package installation to `FeatureManagerService.install_archive`, and activation to `FeatureManagerService.enable`. These operations remain protected by `publisher.manage`, `feature.install`, and `feature.configure.<feature_id>` respectively. Installed package files live in OS-managed application data, not the editable source tree.


## 20. Stage 6 Authentication and Authorization implementation details

- `AuthenticationManager` owns first-administrator setup, credential verification, login lockout,
  and authorized user administration workflows.
- `PasswordHasher` uses scrypt; no plaintext or reversible password storage is permitted.
- `RbacAuthorizationService` implements the public `AuthorizationService` contract and resolves
  permission assignments from the persisted user-role-role-permission relationships.
- Permission matching supports exact IDs, global `*`, and documented namespace wildcards such as
  `feature.view.*` and `feature.configure.*`.
- `SessionManager` stores opaque, process-local session identifiers and enforces idle/absolute expiry.
- `SQLiteUserRepository` owns authentication/RBAC persistence and the `security_audit` table.
- Production bootstrap requires first-run Administrator provisioning and a successful sign-in before
  the main application window is composed. `authenticate=False` is a test/preview-only escape hatch.
- Feature Manager now receives the real RBAC authorization adapter; the previous deny-all adapter
  remains available for fail-closed tests and unconfigured deployments.


## 19. Stage 7 Runtime Implementation Notes

The implementation is owned by `app/feature_manager/runtime.py`; the public runtime
contexts and feature protocol are in `app/feature_manager/runtime_contracts.py`. The
Presentation adapter `app/ui/view_models/feature_runtime.py` converts a feature workspace
into a validated PySide6 `QWidget`. Bootstrap composes the runtime manager and injects
the workspace adapter into the main window.


## 20. Stage 8.1 Feature Configuration Contracts

Feature configuration is owned by `FeatureConfigurationManagerService` in
`app/feature_manager/configuration_manager.py`. The Core `ConfigManager` remains
responsible only for application-global configuration and must not be duplicated.

Public models and operations:

```python
class FeatureConfigurationManager(Protocol):
    def get_configuration(self, feature_id: str, actor_id: str, scope: ConfigurationScope,
                          scope_key: str) -> FeatureConfiguration: ...
    def save_configuration(self, feature_id: str, actor_id: str, scope: ConfigurationScope,
                           scope_key: str, values: Mapping[str, object]) -> FeatureConfiguration: ...
    def reset_configuration(self, feature_id: str, actor_id: str, scope: ConfigurationScope,
                            scope_key: str) -> FeatureConfiguration: ...
```

- Supported scopes are `installation`, `company`, `user`, and `job`. Installation uses the fixed key `default`; other scopes require a non-empty key.
- Every read, write, and reset requires `feature.configure.<feature_id>` at the application boundary. Missing authorization fails closed.
- The schema is loaded from the installed feature package using its manifest-declared relative path. Package containment and symbolic-link checks are enforced.
- Configuration schema uses a documented JSON Schema subset (`type`, `properties`, `required`, `additionalProperties`, `const`, `enum`, string/number/array bounds, `pattern`, and `items`). Unsupported keywords are rejected rather than silently ignored. The optional `x-config-version` integer defaults to `1` and is independent of `data_schema_version`.
- Defaults are read from schema `default` values. Configuration is validated before persistence and again when loaded.
- Profiles are persisted separately from package source by `SQLiteFeatureConfigurationRepository` and migration `0003_feature_configuration.sql`.
- `writeOnly: true` and `x-secret: true` schema properties are rejected because secret values require a dedicated secure secret store; they must not be stored in ordinary JSON profiles.
- A profile with a different schema version is blocked with `FEATURE_CONFIGURATION_MIGRATION_REQUIRED` until the Stage 8.3 migration service explicitly migrates it against the target schema.
- Successful update/reset operations write Feature Registry audit entries and publish `feature.configuration.updated` / `feature.configuration.reset` events.

Stable errors include `FEATURE_PERMISSION_DENIED`, `FEATURE_NOT_CONFIGURABLE`,
`FEATURE_CONFIGURATION_INVALID`, `FEATURE_CONFIGURATION_SCHEMA_INVALID`,
`FEATURE_CONFIGURATION_SCOPE_INVALID`, `FEATURE_CONFIGURATION_SCOPE_KEY_INVALID`,
`FEATURE_CONFIGURATION_SECRET_UNSUPPORTED`, `FEATURE_CONFIGURATION_SCHEMA_UNSUPPORTED`, and
`FEATURE_CONFIGURATION_MIGRATION_REQUIRED`.


## 21. Stage 8.2 Feature Configuration Presentation Contract

The Feature CMS presents schema-driven configuration editing through the existing
`feature.configuration` application service. The Presentation Layer must not read
feature package files, configuration repositories, or SQLite tables directly.

The public manager contract additionally exposes the read-only schema projection:

```python
def get_configuration_schema(
    self, feature_id: str, actor_id: str
) -> FeatureConfigurationSchema: ...
```

`FeatureConfigurationSchema` is a frozen model containing `feature_id`,
`schema_version`, and the validated schema definition. Schema retrieval enforces
`feature.configure.<feature_id>` and verifies the installed package digest before
returning metadata.

Presentation behavior:
- The Feature CMS shows a Configure action only when the current actor is authorized
  for the corresponding feature permission. This visibility check is a usability
  projection; manager operations enforce authorization again.
- Configuration controls are generated from the validated schema properties and do
  not hardcode feature IDs or feature-specific field names.
- Scalar string, integer, number, boolean, and enum fields use typed controls.
  Structured array/object/null values use a JSON editor and are validated by the
  manager on save.
- Installation, company, user, and job scopes are selectable. Installation uses the
  fixed `default` key; other scopes require an explicit scope key (user scope defaults
  to the authenticated actor ID).
- Save and reset operations call the manager contract. The UI never writes persistence
  directly and displays safe validation/error messages.
- Secret-marked schema fields remain unsupported until a dedicated secret store exists.

The UI is implemented in
`app/ui/pages/feature_cms/feature_configuration_dialog.py`; the Feature CMS page
integrates the dialog without changing feature workspace navigation.


## 22. Stage 8.3 Feature Data Migration Contract

The application registers `feature.migrations` through the existing Service Registry.
The public service operations are:

```python
class FeatureDataMigrationEngine(Protocol):
    def migrate_configuration_profiles(
        self, *, feature_id: str, actor_id: str, package_root: Path, target_version: int
    ) -> int: ...
    def migrate_feature_data(
        self, *, feature_id: str, actor_id: str, package_root: Path,
        from_version: int, to_version: int
    ) -> Path: ...
```

- Configuration migrations use `features/<feature_id>/migrations/configuration/NNNN_to_NNNN.json`.
- Feature data migrations use `features/<feature_id>/migrations/data/NNNN_to_NNNN.sql`.
- Migration steps must be sequential, unique, and one version at a time. Missing steps fail closed.
- Configuration operations supported are `rename_field`, `remove_field`, `set_default`, and `map_value`.
- The engine loads the target schema from the verified manifest-declared package file, then transforms and validates profiles before one SQLite repository transaction; each profile retains its scope and creation timestamp.
- Feature data uses an isolated SQLite file per feature. The engine persists the current `data_schema_version` in `feature_data_schema`, verifies the requested source version, and records each applied step in `feature_migration_history` within one transaction.
- Successful data migrations retain a pre-migration SQLite backup. Failed SQL transactions are rolled back and do not leave a partial schema/data change.
- Migration roots must be real directories; symlinks and path escapes are rejected. Migration packages must be verified against the externally provisioned trusted digest allowlist before execution.
- Data migration authorization requires `feature.update`; configuration migration authorization requires `feature.configure.<feature_id>`.
- Stage 8.4 owns coordinated rollback across package, configuration, and feature data state. Automatic Feature Manager update continues to block data schema changes until that coordinator is available.

Stable errors include `FEATURE_MIGRATION_VERSION_INVALID`, `FEATURE_MIGRATION_MANIFEST_INVALID`,
`FEATURE_MIGRATION_PATH_INVALID`, `FEATURE_MIGRATION_DOWNGRADE_UNSUPPORTED`,
`FEATURE_MIGRATION_ALREADY_APPLIED`, `FEATURE_MIGRATION_REPOSITORY_UNSUPPORTED`,
`FEATURE_CONFIGURATION_MIGRATION_MISSING`, `FEATURE_CONFIGURATION_MIGRATION_CONFLICT`,
`FEATURE_CONFIGURATION_MIGRATION_INVALID`, `FEATURE_DATA_MIGRATION_MISSING`,
`FEATURE_DATA_MIGRATION_INVALID`, `FEATURE_DATA_SCHEMA_VERSION_MISMATCH`, and `FEATURE_DATA_MIGRATION_FAILED`.


## 19. Feature Health Check and Rollback Contracts (2.7.0)

The Feature Manager exposes read-only health diagnostics and controlled recovery through
application services. Presentation components must call these services through injected
contracts and must not inspect package files or persistence directly.

### 19.1 Health Check Models

```python
class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass(frozen=True, slots=True)
class HealthCheckItem:
    check_id: str
    status: HealthStatus
    message: str
    error_code: str | None = None

@dataclass(frozen=True, slots=True)
class FeatureHealthReport:
    feature_id: str
    checked_at: datetime
    status: HealthStatus
    checks: tuple[HealthCheckItem, ...]
```

`FeatureHealthCheckService.check_feature(feature_id, actor_id)` checks package digest and
manifest consistency, declared feature/service dependencies, configuration schema and
stored profile compatibility, and the integrity of the feature-owned SQLite data file.
A missing feature data file is healthy when the feature has not created persistent data.

Health checks are diagnostic; they do not silently mutate feature lifecycle state. An
`UNHEALTHY` result must block promotion/activation decisions at the coordinating
application workflow.

### 19.2 Rollback Contract

```python
class FeatureRollbackService(Protocol):
    def create_checkpoint(self, feature_id: str, actor_id: str) -> str: ...
    def complete_checkpoint(self, checkpoint_id: str, actor_id: str) -> None: ...
    def rollback(self, checkpoint_id: str, actor_id: str) -> FeatureRecord: ...
    def recover_pending(self) -> tuple[str, ...]: ...
```

Rules:
- A checkpoint copies the currently registered package only after verifying its digest
  against the registry.
- The checkpoint journal is written atomically and records the prior manifest, package
  digest, package path, lifecycle state, and timestamps.
- Rollback verifies the checkpoint package digest and manifest before restoring it.
- Failed replacement packages are retained inside the checkpoint for diagnostics.
- Recovery only processes journals explicitly marked `prepared`; committed checkpoints
  are retained for audit and may still be used for an explicitly requested rollback.
- The production Feature Manager creates a checkpoint before update, runs post-update
  health checks, commits the checkpoint only after a healthy result, and restores the
  checkpoint when health validation fails.
- Package rollback does not claim to reverse arbitrary external side effects. Database
  restoration must use a separately verified migration backup and a coordinated recovery
  policy.
- Manual rollback requires `feature.update` authorization. Startup recovery is an internal
  application operation and must only use independently trusted checkpoint material.

Events:
- `feature.health_checked`
- `feature.rollback_checkpoint_created`
- `feature.rolled_back`

Errors include:
- `FEATURE_ROLLBACK_CHECKPOINT_INVALID`
- `FEATURE_ROLLBACK_CHECKPOINT_MISSING`
- `FEATURE_ROLLBACK_FAILED`
- `FEATURE_DATA_INTEGRITY_FAILED`
- `FEATURE_CONFIGURATION_INVALID`

Health reports must not include secrets, OCR text, or customer document contents.


Service Registry identifiers:
- `feature.health` — `FeatureHealthCheckService`, version `1.0.0`.
- `feature.rollback` — `FeatureRollbackService`, version `1.0.0`.

The bootstrap composition root registers both services and attempts prepared-checkpoint
recovery before exposing Feature Manager operations. Recovery fails closed when a
checkpoint cannot be independently verified.


## 20. Publisher Trust Management Contracts (2.8.0)

Publisher Trust Manager is the application boundary for trusted feature publishers.
Presentation and Feature Manager code must use this service contract; they must not
read publisher tables or public-key files directly.

### 20.1 Publisher lifecycle

- `register_publisher(publisher_id, display_name, public_key_b64, actor_id)`
- `add_public_key(publisher_id, public_key_b64, actor_id)`
- `revoke_key(publisher_id, key_id, actor_id)`
- `revoke_publisher(publisher_id, actor_id)`
- `list_publishers(actor_id)`
- `list_keys(publisher_id, actor_id)`
- `verify_package(feature_id, package_root)`

All management operations require `publisher.manage`. Public keys are Ed25519 raw
32-byte values encoded as base64. A key ID is derived from the first 24 hexadecimal
characters of the SHA-256 public-key fingerprint. Private keys are never accepted by
the application service or stored in application persistence.

### 20.2 Signed package format

A signed package contains a root-level `publisher_signature.json` envelope:

```json
{
  "signature_schema_version": "1.0",
  "algorithm": "Ed25519",
  "publisher_id": "acme_ocr",
  "key_id": "ed25519-<24-hex-fingerprint>",
  "signature": "<base64-encoded-64-byte-signature>"
}
```

The feature manifest may declare `publisher_id`; signature verification requires it.
The existing `publisher` manifest value must exactly match the registered publisher
display name. This binds the signed package to the trusted publisher identity.

The SHA-256 package digest includes every regular package file except the root-level
`publisher_signature.json` envelope. Symlinks are rejected. The signature signs canonical
UTF-8 JSON with sorted keys and compact separators:

```json
{
  "signature_schema_version": "1.0",
  "algorithm": "Ed25519",
  "publisher_id": "acme_ocr",
  "feature_id": "invoice_reader",
  "version": "1.0.0",
  "package_digest": "sha256:<64-hex-digest>"
}
```

The envelope itself is excluded to avoid a circular digest. The signature still covers
the package digest, which covers the manifest and executable package contents.

### 20.3 Verification and fail-closed rules

- Package verification checks publisher existence and active status, key existence and
  active status, manifest publisher binding, package digest, and Ed25519 signature.
- Unknown, malformed, modified, revoked, or incorrectly bound packages are rejected.
- Revoking a publisher revokes all of its keys. Individual keys can be revoked while
  other active keys remain valid.
- Adding a replacement key does not silently revoke existing keys; key rotation requires
  an explicit old-key revocation after the new key is provisioned and verified.
- A publisher trust change affects subsequent package verification. Existing in-memory
  feature runtimes are not forcibly unloaded by this stage.
- Legacy digest-only verification remains available only when a caller explicitly
  constructs `PackageVerifier` without a Publisher Trust Manager; production bootstrap
  uses Publisher Trust Manager and does not fall back to the legacy allowlist.

Events:
- `publisher.registered`
- `publisher.key_added`
- `publisher.key_revoked`
- `publisher.revoked`

Stable errors include:
- `PUBLISHER_ID_INVALID`
- `PUBLISHER_PUBLIC_KEY_INVALID`
- `PUBLISHER_NOT_FOUND`
- `PUBLISHER_NOT_TRUSTED`
- `PUBLISHER_REVOKED`
- `PUBLISHER_KEY_NOT_TRUSTED`
- `FEATURE_SIGNATURE_MISSING`
- `FEATURE_SIGNATURE_INVALID`

Service Registry identifier: `publisher.trust`, version `1.0.0`.


## 19. Shared Services Foundation and Adapters (Stage 9–10)

Shared Services are engine-neutral in-process capabilities. Public contracts live under `app/services/<service>/interfaces.py`; immutable request/response models live in the corresponding `models.py`. Vendor-specific types and imports must remain inside adapters.

### 19.1 Stable service identifiers

| Service ID | Public interface | Responsibility |
|---|---|---|
| `pdf.render` | `PDFService` | PDF inspection, page rendering, embedded text extraction |
| `ocr.recognize` | `OCRService` | OCR execution and structured recognition result |
| `image.process` | `ImageService` | Crop, deskew, denoise, contrast enhancement |
| `excel.workbook` | `ExcelService` | Workbook inspection, record read/write, output verification |
| `validation.generic` | `ValidationService` | Reusable generic format/required-field checks |
| `reporting.generate` | `ReportService` | Structured processing report generation |

Concrete services are registered at the application composition root through the existing `ServiceRegistry` and typed registration helpers. Stage 10 registers the available PDF and image adapters; Stage 11 adds the OCR adapter. `register_shared_services` remains the aggregate helper for the complete service set. Feature consumers receive only the existing read-only `ServiceProvider`. Service implementations are registered at version `1.0.0`; consumers may request compatible `1.x`.

### 19.2 Data and safety rules

- `NormalizedRegion` uses normalized coordinates in the inclusive `[0, 1]` range and rejects zero-sized or out-of-page regions.
- `ResourceLimits` defines positive ceilings for file bytes, pages, image pixels, and render DPI. Concrete adapters must enforce applicable limits.
- OCR confidence is engine-specific and must not be described as a calibrated probability.
- Service models must not expose PDF/OCR/Excel library objects. Image data crossing the OCR/image boundary is represented by `ImageInput` bytes and a media type.
- Excel identifiers remain strings by default; concrete adapters must preserve leading zeroes and use temporary output, verification, and promotion rather than modifying the source workbook by default.
- Reports must avoid embedding raw OCR text or sensitive document fields by default.
- Service contracts do not contain tax-invoice or other document-specific business rules.

### 19.3 Adapter readiness

Stage 9 established contracts, models, stable identifiers, and test registration. Stage 10 added PDF and image adapters without changing their public Protocol signatures. Stage 11 adds a concrete OCR adapter without changing the public `OCRService` signature. Excel production adapter remains deferred.

### 19.4 Stage 10 adapter behavior

- `PdfiumAdapter` implements `PDFService` using pypdfium2/PDFium. It validates path, extension, file size, encryption, page count, page index, DPI, and rendered pixel count. It returns PNG bytes and never writes to the source PDF.
- `OpenCVImageAdapter` implements `ImageService` using Pillow and OpenCV. It accepts encoded PNG, JPEG, TIFF, BMP, and WEBP inputs, applies EXIF orientation, enforces byte/pixel limits, and returns PNG bytes in a new `ImageInput`.
- Supported image profiles are `light`, `standard`, and `strong` for denoising and contrast enhancement. Unsupported profile names fail with `IMAGE_PROFILE_INVALID`.
- Image transformations do not mutate the input bytes. Deskew is intentionally conservative and leaves images unchanged when a reliable small skew angle cannot be estimated.
- Concrete adapters raise `ApplicationError` with stable codes and safe messages; vendor exceptions must not cross the service boundary.
- Stage 10 registers `pdf.render` and `image.process` at the application composition root. The full six-service registration helper remains available for the point when all concrete adapters exist.


### 19.5 Stage 11 OCR adapter behavior

- `TesseractOCRAdapter` implements the existing `OCRService.recognize(ImageInput, OCROptions) -> OCRResult` contract using `pytesseract`; no public OCR model or Protocol signature changes are made.
- The adapter accepts PNG, JPEG, TIFF, BMP, and WEBP encoded images, validates declared media type, encoded byte size, decoded pixel count, language identifiers, and page segmentation mode.
- Tesseract returns word-level text, bounding boxes, and engine confidence scores. Words are grouped into lines using Tesseract block/paragraph/line identifiers. The aggregate confidence is the arithmetic mean of accepted word confidence scores and remains explicitly tagged `engine_score`, not a calibrated probability.
- Empty recognition output returns empty text/lines and `confidence_kind="unavailable"`.
- OCR execution uses a configurable timeout. The adapter maps missing executable, missing language packs, invalid input/options, and engine failures to stable `ApplicationError` codes; vendor exceptions do not cross the service boundary.
- The composition root registers `ocr.recognize` at service version `1.0.0`. Tesseract executable and language data are external deployment prerequisites and must be bundled/provisioned for offline use.
- Stage 11 error codes: `OCR_ENGINE_UNAVAILABLE`, `OCR_LANGUAGE_UNAVAILABLE`, `OCR_INPUT_INVALID`, `OCR_FILE_SIZE_LIMIT`, `OCR_IMAGE_FORMAT_UNSUPPORTED`, `OCR_MEDIA_TYPE_MISMATCH`, `OCR_IMAGE_PIXEL_LIMIT`, `OCR_IMAGE_DECODE_FAILED`, `OCR_OPTIONS_INVALID`, and `OCR_EXECUTION_FAILED`.


## 19.6 Stage 12 — Excel Engine Adapter

`OpenpyxlExcelAdapter` in `app/services/excel/adapters/openpyxl_adapter.py` implements
the existing `ExcelService` protocol. The adapter is registered at the composition root
as `excel.workbook` version `1.0.0`; it is a Shared Service, not a Feature Module.

The adapter:
- Inspects `.xlsx` and `.xlsm` workbooks and returns worksheet names, format, macro
  presence, and warnings for workbook features with round-trip limitations.
- Reads configured columns by exact header label or Excel column letters and returns
  immutable `ExcelRecord` values with original worksheet row numbers.
- Supports mapping-based key matching with explicit key type, normalization, duplicate,
  unmatched, and overwrite policies.
- Preserves text identifiers and leading zeroes; numeric key normalization uses Decimal.
- Never evaluates workbook formulas or extracted formula-like strings.
- Writes to a temporary copy in the destination directory, verifies the staged workbook,
  and atomically promotes it. The source workbook is never the output destination.
- Translates vendor/file errors into stable `ApplicationError` codes.

The adapter uses `openpyxl` only inside its concrete adapter boundary. It does not expose
openpyxl workbook, worksheet, cell, or style objects through public contracts.


## 22. Stage 13.1 — Tax Invoice Feature Contracts (2.13.0)

Stage 13.1 introduces typed, immutable application job contracts and feature-owned
Tax Invoice data models. These contracts prepare the feature workflow and workspace
without adding extraction behavior or a background Job Orchestrator.

### 22.1 Application job models

`app.core.job_contracts` provides `JobRequest`, `JobProgress`, `FileResult`, and
`JobResult` as immutable dataclasses. `JobRequest.configuration`,
`FileResult.extracted_fields`, and `FileResult.confidence` are read-only mapping
projections. `JobProgress` is a safe progress-only model and must not carry OCR text
or extracted document values. Confidence values remain engine-specific scores; the
contract checks finiteness but does not reinterpret them as probabilities or impose
a universal scale. `JobResult` validates aggregate counts against its per-file results.

### 22.2 Tax Invoice feature models

The `features.tax_invoice.models` package owns:
- `TaxInvoiceFieldValue`: raw and normalized identifier values remain separate;
  confidence semantics and zero-based source page are explicit.
- `TaxInvoicePageDetection`: page-level candidate decision, normalized search region,
  matched markers, reason codes, and fallback indicator.
- `TaxInvoiceExtraction`: one source PDF's page count, detections, extracted tax
  invoice number, related invoice number, warnings, status, and stable error code.

The initial MVP identifier scope is `tax_invoice_number` and `invoice_number`.
Additional seller/buyer tax identity, dates, amounts, or line items are not part of
this Stage 13.1 contract and require a separately reviewed scope change. PDF page
indexes are zero-based internally.

### 22.3 Feature-specific execution contract

`features.tax_invoice.contracts.TaxInvoiceFeatureContract` specializes the existing
FeatureModule lifecycle with a typed `JobRequest` input and `JobResult` output. It
continues to use the existing `FeatureContext`, `UIContext`, and `FeatureDescriptor`;
it does not create a second runtime or service registry. The concrete entry point,
manifest, configuration schema, detection, extraction, normalization, validation,
Excel workflow, and workspace are delivered in subsequent Stage 13 increments.

### 22.4 Error and confidence handling

Per-file failures require a stable `error_code`. Confidence is optional and is retained
as an engine score with its declared semantics; no confidence threshold or identifier
normalization is defined by these data contracts. Ambiguous results are represented
with the `review` status rather than silently repaired.


## 23. Stage 13.2 — Tax Invoice Feature Manifest and Configuration

The `features/tax_invoice/manifest.json` package manifest declares the stable feature ID
`tax_invoice`, package version `1.0.0`, initially API contract compatibility `2.13.0` (advanced to `2.14.0` in Stage 13.4 and `2.15.0` in Stage 13.5), the runtime
entry point, permissions, license entitlement, workspace target, and required Shared
Services. The feature uses the existing Feature Manager and Service Registry; it does not
create a private service registry or duplicate PDF/OCR/image/Excel adapters.

Declared service dependencies are `pdf.render`, `ocr.recognize`, `image.process`,
`excel.workbook`, and `validation.generic`, each pinned to `1.0.0`. The Feature Runtime
therefore exposes only these declared services to the feature instance.

The feature configuration contract is defined by `config_schema.json`, independently
versioned by `x-config-version: 1`. Stage 13.3 added optional `processing.render_dpi`
with a default of 200 without changing the configuration version; older profiles that omit
the optional key continue to use this default. Configuration groups are `detection`, `ocr`, and
`processing`. Defaults are a top-region ratio of `0.25`, marker phrases `FAKTUR PAJAK`
and `FAKTURPAJAK`, disabled full-page fallback, preference for embedded PDF text, OCR
language `ind+eng`, and a maximum of 200 pages per document. The OCR adapter must verify
traineddata availability when executing a job.

The schema intentionally avoids a universal confidence threshold: OCR confidence remains
engine-specific under the Stage 13.1 contracts. Configuration is validated and persisted by
the existing Feature Configuration Manager, including authorization, package digest,
schema-version, and profile-scope checks.

The manifest itself is not a cryptographic signature; package authenticity remains governed
by the existing publisher trust and package verification process.


## 24. Stage 13.3 — Tax Invoice Detection and Extraction

The Tax Invoice feature now owns page-candidate detection in `detector.py` and raw field
extraction orchestration in `extractor.py`. It consumes only the public `PDFService` and
`OCRService` interfaces resolved from the injected Feature Runtime service provider. No
PDF/OCR adapter or engine is instantiated by the feature.

For each PDF, the processor inspects metadata, rejects encrypted documents, and enforces
the configured page ceiling before rendering. If embedded PDF text is preferred and
contains a configured marker, that page becomes a candidate without invoking OCR. Embedded
PDF text extraction does not expose text geometry through the current PDF contract, so
marker detection on that path is page-wide; the recorded search region remains the configured
top-region policy and must not be interpreted as proof of text coordinates. When embedded
text does not identify a candidate, the processor renders the configured top-page region and
runs OCR. Optional full-page fallback is invoked only when enabled. Candidate scanned pages
are then rendered and OCRed at full-page resolution for field extraction.

The current MVP extracts only `tax_invoice_number` and `invoice_number`. It preserves the
raw matched text and source page index; `normalized_value` remains null until Stage 13.4.
OCR confidence is retained only as an engine-specific score. Missing markers or fields
produce `review` outcomes and warnings rather than invented values. Per-file failures are
isolated in the application `JobResult`; Excel output remains deferred to Stage 13.5.

The version 1 configuration schema adds optional `processing.render_dpi` (default `200`,
allowed range `100`–`400`). The extractor uses `200` when an existing configuration profile
does not contain this optional key, so no persisted-profile migration is required.


## 25. Stage 13.4 — Tax Invoice Normalization and Validation

Stage 13.4 adds feature-owned normalization and validation for the two MVP identifiers.
`TaxInvoiceFieldValue.raw_value` remains the exact extracted candidate;
`normalized_value` is populated only when the corresponding rule accepts the value.

Tax invoice numbers accept either 16 ASCII digits or the grouped form
`000.000-00.00000000`. The normalizer converts accepted compact digits into the grouped
form. It does not substitute visually similar OCR characters, infer missing digits, or
accept other punctuation. This format check does not independently establish tax validity
or verify an issuing authority's allocation.

Invoice numbers are normalized using Unicode NFKC and removal of all whitespace characters
(including spaces, tabs, and line breaks). Case and punctuation are preserved because invoice
numbering is issuer-defined. The original OCR candidate remains unchanged in `raw_value`.
Empty, overlong, control-character-only, or punctuation-only values are rejected.

The validator reports each field as `valid`, `invalid`, `missing`, or `conflict`. Multiple
occurrences are compared after normalization: repeated equivalent values are accepted, while
different valid normalized values produce a conflict and require manual review. A document
is `success` only when both MVP fields validate and neither field conflicts; otherwise it is
`review`. The result model exposes an optional `TaxInvoiceValidation` summary, preserving
compatibility for callers constructing older extraction records.

The application API contract version advanced to `2.14.0` for this additive validation
result contract; Stage 13.5 advances it to `2.15.0` for Excel key normalization and output mapping. No database migration or configuration schema migration is required.


## 26. Stage 13.5 Tax Invoice Excel Mapping and Output

The Tax Invoice feature may optionally receive an `excel` configuration object. When present,
`source_workbook_path` identifies the existing workbook to read, while `JobRequest.output_path`
identifies a separate destination workbook. The source workbook must never be overwritten.

The mapping declares the worksheet, header/data rows, source key column, target column,
`match_field`, `write_field`, key type, normalization profile, duplicate policy, unmatched
policy, and overwrite policy. The match and write fields must be different Tax Invoice
identifiers. For invoice-number matching, `remove_whitespace` is the recommended profile so
workbook keys are normalized consistently with the Tax Invoice feature's invoice
`normalized_value` rule.

**Mandatory write eligibility rule:** only per-file results whose status is `success` may be
passed to the Excel write service. Results with status `review` (presented to users as
**Need Review**), `failed`, or `skipped` must never be included in Excel write records.
A success result missing a required normalized mapping value is downgraded to `review`
before writing. If there are no eligible successful records, no output workbook is created.

The Excel service performs the configured matching and duplicate/unmatched/overwrite
policies, writes to a staged copy, verifies the result, and promotes it to the destination.
The output path is reported only after successful write verification.


## 27. Stage 13.6 Tax Invoice GUI Workspace

The Tax Invoice workspace is the manifest-declared `ui:TaxInvoiceWorkspace` target and is
created only through `FeatureRuntimeManager.create_workspace` with the supplied `UIContext`.
It is feature-owned presentation code; it must not be moved into Core or instantiate PDF, OCR,
image, or Excel adapters.

The workspace collects PDF input paths, feature processing options, optional Excel mapping,
and a separate output workbook destination. It constructs the existing immutable `JobRequest`
and invokes the initialized feature runtime from a dedicated Qt worker thread. The GUI thread
must never execute PDF rendering, OCR, validation, or workbook operations. The worker returns
the existing `JobResult`; no new job persistence or database contract is introduced by this stage.

The user-facing result labels are exactly **Success**, **Need Review**, and **Failed**. The
internal application status remains `success`, `review`, and `failed`; internal `skipped`
records, if surfaced, are grouped under **Need Review** for this workspace. Excel write
eligibility remains governed by Stage 13.5: only internal `success` results may be written.

The workspace displays per-file status, confidence when supplied by the OCR engine, extracted
identifiers, warnings, and error codes. When no confidence value is supplied, the UI displays
an em dash rather than inventing a score. The progress indicator is indeterminate while the
current synchronous feature workflow is executing on the worker thread; it must not imply
per-file progress that the feature does not currently publish.

No API contract version increment is required: this stage composes existing `UIContext`,
`JobRequest`, and `JobResult` contracts without changing their public shapes.


## 28. Stage 13.7 Tax Invoice Integration and Failure Semantics

Stage 13.7 hardens the feature's existing `JobRequest`/`JobResult` workflow without changing
the public contract shapes or API contract version. The feature boundary applies these rules:

- A per-file extraction result with internal status `success` is eligible for Excel mapping.
- Internal `review`, `failed`, and `skipped` results are never passed to the Excel write service.
- If Excel completes but reports zero written rows, affected successful extraction results become
  internal `review`; the job does not report an output workbook path. The GUI presents this as
  **Need Review**.
- A documented `ApplicationError` from Excel mapping/output converts affected successful
  extraction results to `failed` using the stable error code from the service.
- An unexpected adapter/library exception is contained at the feature boundary, logged for
  diagnostics, and converts affected successful results to `failed` with
  `TAX_INVOICE_EXCEL_OUTPUT_FAILED`. Internal exception details are not exposed in `JobResult`.
- A mixed batch remains a per-file result: a failed or review document does not erase other
  successfully processed documents. Aggregate counters must match the per-file results.

Integration tests use synthetic document outcomes and the real Excel adapter to verify that a
mixed Success/Need Review/Failed batch writes only the successful document and leaves the source
workbook unchanged. No database persistence or new event contract is introduced here.
