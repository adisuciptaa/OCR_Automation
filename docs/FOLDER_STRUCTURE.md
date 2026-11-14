# OCR Automation — Folder Structure Standard

**Document ID:** OCRA-FS-001  
**Version:** 2.0.0  
**Status:** Approved Architecture Baseline  
**Last Updated:** 2026-11-13

## 1. Purpose

This document defines the canonical repository layout. All developers and AI coding agents must follow it. A folder or file may be added only when its ownership and purpose are documented.

## 2. Canonical Structure

```text
OCR_AUTOMATION/
│
├── app/
│   ├── main.py
│   ├── bootstrap.py
│   │
│   ├── core/
│   │   ├── job_contracts.py
│   │   ├── application.py
│   │   ├── lifecycle.py
│   │   ├── config_manager.py
│   │   ├── event_bus.py
│   │   ├── job_orchestrator.py
│   │   ├── service_registry.py
│   │   ├── logging_config.py
│   │   └── exceptions.py
│   │
│   ├── feature_manager/
│   │   ├── discovery.py
│   │   ├── manifest_loader.py
│   │   ├── registry.py
│   │   ├── lifecycle_manager.py
│   │   ├── installer.py
│   │   ├── updater.py
│   │   ├── uninstaller.py
│   │   ├── package_verifier.py
│   │   ├── publisher_trust.py
│   │   ├── contracts.py
│   │   ├── runtime.py
│   │   └── runtime_contracts.py
│   │
│   ├── services/
│   │   ├── ocr/
│   │   │   ├── interfaces.py
│   │   │   ├── models.py
│   │   │   └── adapters/
│   │   ├── pdf/
│   │   │   ├── interfaces.py
│   │   │   └── adapters/
│   │   │       └── pypdfium2_adapter.py
│   │   ├── image/
│   │   │   ├── interfaces.py
│   │   │   └── adapters/
│   │   │       └── opencv_adapter.py
│   │   ├── excel/
│   │   │   ├── interfaces.py
│   │   │   ├── models.py
│   │   │   └── adapters/
│   │   ├── validation/
│   │   └── reporting/
│   │
│   ├── security/
│   │   ├── authentication.py
│   │   ├── authorization.py
│   │   ├── contracts.py
│   │   ├── models.py
│   │   ├── password_hasher.py
│   │   ├── session_manager.py
│   │   ├── audit.py
│   │   └── license_manager.py
│   │
│   ├── persistence/
│   │   ├── database.py
│   │   ├── migrations/
│   │   │   ├── 0001_feature_registry.sql
│   │   │   ├── 0002_authentication.sql
│   │   │   ├── 0003_feature_configuration.sql
│   │   │   └── 0004_publisher_trust.sql
│   │   └── repositories/
│   │       ├── feature_registry_repository.py
│   │       ├── user_repository.py
│   │       ├── feature_configuration_repository.py
│   │       └── publisher_trust_repository.py
│   │
│   └── ui/
│       ├── application_window.py
│       ├── navigation/
│       │   └── navigation_controller.py
│       ├── pages/
│       │   ├── dashboard/
│       │   ├── feature_cms/
│       │   ├── settings/
│       │   ├── users/
│       │   │   └── user_management_page.py
│       │   ├── history/
│       │   └── reports/
│       ├── components/
│       │   ├── sidebar.py
│       │   └── application_header.py
│       ├── dialogs/
│       │   └── authentication_dialogs.py
│       └── view_models/
│           ├── feature_catalog.py
│           ├── feature_management.py
│           └── feature_runtime.py
│
├── features/
│   ├── tax_invoice/
│   │   ├── manifest.json
│   │   ├── config_schema.json
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── contracts.py
│   │   ├── entry.py
│   │   ├── models.py
│   │   ├── ui.py
│   │   ├── detector.py
│   │   ├── extractor.py
│   │   ├── excel_output.py
│   │   ├── validator.py
│   │   ├── normalizer.py
│   │   ├── ui/
│   │   ├── migrations/
│   │   │   ├── configuration/
│   │   │   └── data/
│   │   └── tests/
│   │
│   ├── invoice_reader/
│   ├── receipt_reader/
│   └── purchase_order_reader/
│
├── config/
│   ├── defaults/
│   ├── schemas/
│   └── templates/
│
├── database/
│   └── .gitkeep
│
├── runtime/
│   ├── input/
│   ├── output/
│   ├── temporary/
│   ├── quarantine/
│   ├── logs/
│   ├── reports/
│   └── backups/
│
├── models/
│   └── README.md
│
├── packages/
│   └── .gitkeep
│
├── installer/
│   ├── build/
│   └── scripts/
│
├── tools/
│   ├── sign_feature_package.py
│   ├── create_dev_publisher_key.py
│   └── build_feature_package.py
│
├── scripts/
│   ├── setup_test_environment.ps1
│   ├── run_all_tests.ps1
│   ├── run_gui_tests.ps1
│   └── verify_environment.py
│
├── .github/
│   └── workflows/
│       └── windows-python312-tests.yml
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── gui/
│   ├── contract/
│   ├── system/
│   ├── security/
│   └── fixtures/
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── FOLDER_STRUCTURE.md
│   ├── MODULE_REGISTRY.md
│   ├── API_CONTRACTS.md
│   ├── DEVELOPMENT_STANDARD.md
│   ├── CHANGELOG.md
│   ├── TESTING_GUIDE.md
│   ├── GITHUB_SETUP.md
│   └── FEATURE_MIGRATION_GUIDE.md
│
├── pyproject.toml
├── README.md
└── LICENSE
```

This is the target structure. It does not authorize creating every empty directory immediately. Create directories when the corresponding implementation is introduced.

## 3. Directory Ownership

| Path | Ownership | Allowed content |
|---|---|---|
| `app/core/` | Core | Lifecycle, orchestration, event bus, configuration, service registry, structured exceptions, and logging configuration |
| `app/feature_manager/` | Feature Manager | Discovery, registry, validation, install/update/uninstall, publisher trust, signature verification, trusted runtime loading, health checks, migrations, and rollback coordination |
| `app/services/` | Shared Services | Reusable PDF/OCR/image/Excel/validation/reporting interfaces and adapters |
| `app/security/` | Security | Authentication, authorization, password hashing, session lifecycle, audit, license validation |
| `app/persistence/` | Persistence | Database connection, ordered migrations, Feature Registry, publisher trust, and user/security repositories |
| `app/ui/` | Presentation | PySide6 windows, pages, components, view models |
| `features/<feature_id>/` | Feature owner | Business-specific workflow, extraction, validation, UI, config schema |
| `config/` | Configuration | Defaults, schemas, and reusable template profiles |
| `runtime/` | Runtime | User data, temporary artifacts, logs, reports, backups |
| `models/` | Model assets | Offline OCR model metadata and approved model files |
| `packages/` | Repository package staging | Optional developer-produced package artifacts; local signed packages should be stored outside Git |
| OS application data `features/installed/` | Runtime | Verified feature packages installed by Feature Manager; never the editable source tree |
| `installer/` | Release engineering | Build scripts and installer configuration |
| `tools/` | Maintainer tooling | Offline publisher key generation and feature package build/sign utilities; private keys remain outside the repository |
| `tests/` | Quality | Automated tests and test fixtures |
| `docs/` | Documentation | Architecture, contracts, standards, changelog, test guide |

## 4. Naming Rules

- Python packages and modules: `snake_case`.
- Classes: `PascalCase`.
- Functions and variables: `snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- Feature IDs: lowercase `snake_case`, stable after publication.
- Manifest filename: exactly `manifest.json`.
- Configuration schema filename: `config_schema.json`.
- Test files: `test_<subject>.py`.
- Avoid vague names such as `helper.py`, `common.py`, or `misc.py`; use an explicit responsibility.

## 5. Import and Dependency Rules

Allowed dependency direction:

```text
UI → Application/Core Contracts
Core → Feature Manager + Service Interfaces + Security Interfaces
Feature Manager → Feature Contracts + Package Verification
Feature Modules → Public Shared Service Interfaces + Feature Contracts
Service Adapters → Service Interfaces + Infrastructure Libraries
Infrastructure → Persistence / OS / External Libraries
```

Rules:
- Feature modules must not import another feature's internal implementation.
- Feature modules must not import GUI internals from other features.
- UI must not import OCR/PDF/Excel engine adapters directly.
- Business features must call services through public interfaces.
- Shared Services must not import feature modules.
- Core must not import a specific business feature by name.
- Avoid circular imports. Use contracts, dependency injection, or events.
- Only the composition/bootstrap layer may assemble concrete implementations.

## 6. Runtime Data Separation

Runtime data must not be mixed with source code.

- `runtime/input/`: optional default input staging area.
- `runtime/output/`: generated output files.
- `runtime/temporary/`: intermediate images, temporary workbooks, and transient artifacts.
- `runtime/quarantine/`: untrusted or invalid packages/files awaiting review.
- `runtime/logs/`: application and job logs.
- `runtime/reports/`: generated job reports.
- `runtime/backups/`: controlled backups.

Production paths should be configurable and may be redirected to user-selected locations. Never assume the current working directory is the application data directory.

Do not commit customer documents, credentials, license secrets, OCR caches, or database files to source control.

## 7. Feature Package Layout

A feature package should contain only what it owns:

```text
features/
└── tax_invoice/
    ├── manifest.json
    ├── __init__.py
    ├── contracts.py
    ├── models.py
    ├── plugin.py
    ├── workflow.py
    ├── detector.py
    ├── extractor.py
    ├── validator.py
    ├── normalizer.py
    ├── config_schema.json
    ├── ui.py             # Feature-owned PySide6 workspace (when required)
    ├── ui/               # Optional workspace subcomponents
    ├── migrations/
    └── tests/
```

Not every feature needs every file. Keep the package minimal. A feature must not copy generic PDF rendering, OCR engine setup, Excel workbook loading, user authentication, or audit infrastructure into its own directory.

## 8. Adding a New Folder or File

Before adding a path:
1. Search the existing repository and Module/Feature Registry.
2. Identify the owning layer.
3. Check whether an existing module already provides the responsibility.
4. Explain why a new path is needed.
5. Update this document and relevant registry/contracts when the path changes the architecture.
6. Add tests where applicable.

## 9. Prohibited Structure Changes

Without explicit approval:
- Do not rename or move existing modules.
- Do not create a second Core, Feature Manager, Service Registry, or OCR engine manager.
- Do not create duplicate service implementations for a feature-specific convenience.
- Do not put runtime files inside source directories.
- Do not allow a feature package to modify files belonging to another feature.
- Do not create a second configuration source for the same setting.


## 10. Implemented Foundation Files — Stage 1

The following files have been introduced as the first executable application slice:

| Path | Owner | Responsibility |
|---|---|---|
| `app/main.py` | Process entry point | Delegates startup to bootstrap, shows the main window, starts the Qt event loop, and returns an exit code |
| `app/bootstrap.py` | Composition root | Creates/reuses QApplication, configures logging, assembles Core services, and creates the initial window |
| `app/core/application.py` | Core | Coordinates application runtime initialization and shutdown |
| `app/core/lifecycle.py` | Core | Enforces valid application lifecycle state transitions |
| `app/core/config_manager.py` | Core | Loads, merges, and atomically saves application-level JSON configuration |
| `app/core/event_bus.py` | Core | Publishes typed in-process application events |
| `app/core/service_registry.py` | Core | Registers services at composition time and exposes a read-only provider contract |
| `app/core/logging_config.py` | Core | Configures centralized console and optional rotating-file logging |
| `app/core/exceptions.py` | Core | Defines structured application exceptions and stable error codes |
| `app/ui/application_window.py` | Presentation | Owns the minimal PySide6 main window shell |
| `app/__init__.py` | Python package | Marks the application package |
| `app/ui/__init__.py` | Python package | Marks the presentation package |

The Core files implement the initial lifecycle, configuration, event, service-provider,
logging, and runtime-startup responsibilities. They do not implement feature discovery,
authentication, authorization, persistence repositories, OCR/PDF/Excel services, or
business workflows; those remain assigned to their canonical modules.

## 11. Implemented GUI Files — Stage 4

| Path | Owner | Responsibility |
|---|---|---|
| `app/ui/application_window.py` | Presentation | Main window composition, page hosting, and feature workspace delegation |
| `app/ui/components/sidebar.py` | Presentation | Static navigation and dynamic feature navigation controls |
| `app/ui/components/application_header.py` | Presentation | Current page title, subtitle, and runtime status |
| `app/ui/navigation/navigation_controller.py` | Presentation | Validates navigation targets against the current UI feature projection; not an authorization service |
| `app/ui/pages/dashboard/dashboard_page.py` | Presentation | Dashboard overview and dynamic feature cards |
| `app/ui/pages/feature_cms/feature_cms_page.py` | Presentation | Read-only Feature Registry listing; lifecycle mutations remain application-service operations |
| `app/ui/pages/settings/settings_page.py` | Presentation | Application settings landing page |
| `app/ui/view_models/feature_catalog.py` | Presentation | Display-only feature summary and catalog/workspace adapter protocols |
| `tests/unit/test_application_window.py` | Quality | GUI composition, navigation, dynamic catalog, and workspace delegation tests |

The GUI does not implement Feature Manager lifecycle operations or authorization. It displays a read-only registry projection and delegates feature navigation through the authorized catalog contract. The application service remains the authorization boundary.


## 10. Stage 5 paths introduced

```text
app/
├── feature_manager/
│   ├── __init__.py
│   ├── contracts.py
│   ├── defaults.py
│   ├── discovery.py
│   ├── installer.py
│   ├── lifecycle_manager.py
│   ├── manager.py
│   ├── manifest_loader.py
│   ├── models.py
│   ├── package_verifier.py
│   ├── registry.py
│   ├── updater.py
│   ├── uninstaller.py
│   └── schemas/manifest.schema.json
├── persistence/
│   ├── __init__.py
│   ├── migrations/0001_feature_registry.sql
│   └── repositories/feature_registry_repository.py
└── ui/view_models/
    └── feature_management.py

tests/unit/feature_manager/
```

The `feature_manager` package owns lifecycle orchestration and package handling. The
persistence adapter owns SQLite details. UI view models expose read-only projections only.


## Stage 7 Paths Introduced

| Path | Owner | Responsibility |
|---|---|---|
| `app/feature_manager/runtime.py` | Feature Manager | Verified feature loading, activation, instance reuse, shutdown, and module namespace cleanup |
| `app/feature_manager/runtime_contracts.py` | Feature Manager contracts | Immutable `FeatureContext` / `UIContext` and the public `FeatureModule` protocol |
| `app/ui/view_models/feature_runtime.py` | Presentation adapter | Converts runtime workspace creation into a validated PySide6 `QWidget` |
| `tests/unit/feature_manager/test_runtime.py` | Quality | Runtime contract, activation, lifecycle cleanup, and entry-point rejection tests |
| `tests/integration/test_feature_runtime_activation.py` | Quality | End-to-end Feature Manager to runtime activation and tamper rejection tests |


## Stage 8.1 Paths Introduced

| Path | Owner | Responsibility |
|---|---|---|
| `app/feature_manager/configuration_manager.py` | Feature Manager | Authorized feature configuration orchestration, schema validation, defaults, version checks, audit, and events |
| `app/persistence/repositories/feature_configuration_repository.py` | Persistence | SQLite CRUD for feature configuration profiles |
| `app/persistence/migrations/0003_feature_configuration.sql` | Persistence | Creates scoped, versioned configuration profile storage |
| `tests/unit/feature_manager/test_configuration_manager.py` | Quality | Authorization, validation, defaults, reset, version mismatch, and secret-field rejection |
| `tests/unit/feature_manager/test_configuration_repository.py` | Quality | Persistence round-trip and scope isolation |


## Stage 8.3 Paths Introduced

| Path | Owner | Responsibility |
|---|---|---|
| `app/feature_manager/migration_engine.py` | Feature Manager | Sequential configuration and feature-data migration orchestration, authorization, validation, transactions, backups, and events |
| `features/<feature_id>/migrations/configuration/` | Feature package | Declarative JSON configuration profile migrations (`NNNN_to_NNNN.json`) |
| `features/<feature_id>/migrations/data/` | Feature package | Reviewed SQLite feature-data migrations (`NNNN_to_NNNN.sql`) |
| `runtime/database/features/` | Runtime | Isolated SQLite data store for each feature |
| `runtime/backups/migrations/` | Runtime | Pre-migration feature database backups |
| `tests/unit/feature_manager/test_migration_engine.py` | Quality | Configuration and SQLite data migration behavior, failure rollback, and SQL restrictions |
| `docs/FEATURE_MIGRATION_GUIDE.md` | Documentation | Migration file format, supported operations, security, and current limitations |


## 10. Stage 9 Shared Services Foundation Paths

The following paths are now introduced under the existing `app/services/` owner:

```text
app/services/
├── __init__.py
├── models.py
├── registration.py
├── pdf/
│   ├── __init__.py
│   ├── interfaces.py
│   └── models.py
├── ocr/
│   ├── __init__.py
│   ├── interfaces.py
│   └── models.py
├── image/
│   ├── __init__.py
│   └── interfaces.py
├── excel/
│   ├── __init__.py
│   ├── interfaces.py
│   └── models.py
├── validation/
│   ├── __init__.py
│   ├── interfaces.py
│   └── models.py
└── reporting/
    ├── __init__.py
    ├── interfaces.py
    └── models.py
```

`registration.py` is a composition-root helper. It does not create a second registry and must not be called by feature packages. Adapter implementations belong in each service's `adapters/` directory when selected and implemented.


## 11. Stage 10 PDF and Image Adapter Paths

```text
app/services/pdf/adapters/
├── __init__.py
└── pypdfium2_adapter.py

app/services/image/adapters/
├── __init__.py
└── opencv_adapter.py

tests/unit/services/pdf/
└── test_pypdfium2_adapter.py

tests/unit/services/image/
└── test_opencv_adapter.py
```

These adapters are Shared Services implementations, not Feature Modules. Vendor imports remain inside adapter modules.


## 12. Stage 11 OCR Adapter Paths

```text
app/services/ocr/
├── interfaces.py
├── models.py
└── adapters/
    ├── __init__.py
    └── tesseract_adapter.py

tests/unit/services/ocr/
└── test_tesseract_adapter.py
```

The Tesseract adapter is a Shared Service implementation, not a Feature Module. Keep `pytesseract` and Tesseract-specific handling inside the adapter. The executable and language data are deployment assets and must not be copied into a feature package.


## 13. Stage 12 Excel Adapter Paths

```text
app/services/excel/
├── __init__.py
├── interfaces.py
├── models.py
└── adapters/
    ├── __init__.py
    └── openpyxl_adapter.py

tests/unit/services/excel/
├── __init__.py
└── test_openpyxl_adapter.py
```

`openpyxl_adapter.py` is the only layer permitted to import openpyxl. Public models and
`ExcelService` remain engine-neutral. The adapter is registered by the existing
`app/services/registration.py` composition-root helper.


### Stage 13.4 feature files

- `features/tax_invoice/normalizer.py`: feature-owned identifier normalization.
- `features/tax_invoice/validator.py`: feature-owned field and document validation.
