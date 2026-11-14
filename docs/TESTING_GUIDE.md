# OCR Automation — Testing Guide

**Baseline:** 2.0.0  
**Status:** Initial testing standard

## 1. Purpose

This guide defines the minimum testing approach for OCR Automation. It complements
`DEVELOPMENT_STANDARD.md` and `API_CONTRACTS.md`.

## 2. Testing layers

| Test type | Purpose |
|---|---|
| Unit | Verify an individual function, class, or module in isolation |
| Contract | Verify public interfaces, schemas, models, and error behavior |
| Integration | Verify collaboration between Core, Feature Manager, Shared Services, and adapters |
| System | Verify complete user workflows from input to output |
| Security | Verify authentication, authorization, file handling, package verification, and audit controls |
| GUI / Manual | Verify visible interactions, progress, warnings, and accessibility/usability |

## 3. Required test cases

Critical document-processing workflows must cover:

- Valid input.
- Invalid or corrupt input.
- Empty input.
- Duplicate identifiers.
- Unmatched identifiers.
- Low-confidence or ambiguous OCR results.
- Cancellation.
- Partial failure.
- Output write failure.
- Recovery after interruption.

## 4. OCR-specific testing

- Use synthetic or approved test documents.
- Record expected text and extraction results.
- Test different scan quality, rotation, skew, resolution, and page layouts.
- Verify preprocessing and fallback behavior.
- Treat OCR confidence as an engine-provided signal, not a correctness probability.
- Verify uncertain values are routed to manual review rather than silently accepted.
- Record OCR engine and model versions where practical.

Stage 11 OCR adapter tests should additionally cover image media-type validation, corrupt and oversized images, pixel limits, invalid OCR options, missing engine, missing language packs, timeout/engine failure, empty output, word geometry, line grouping, confidence semantics, and service registration. Unit tests should mock the Tesseract boundary so the regular test suite does not require a local executable or language packs.

## 5. PDF and image testing

- Verify page count and metadata handling.
- Verify rendering at configured DPI.
- Verify corrupted, encrypted, oversized, and unsupported PDFs are handled safely.
- Verify image crop, deskew, denoise, threshold, and normalization behavior.
- Confirm source PDFs remain unchanged.

## 6. Excel testing

- Test valid and invalid workbooks, worksheets, headers, and mappings.
- Test identifiers with leading zeroes and formatting-sensitive values.
- Test duplicates, unmatched rows, and overwrite policies.
- Verify the original workbook remains untouched by default.
- Write to a temporary copy, verify the result, then promote it.
- Test formulas, styles, worksheets, and representative workbook features supported by the chosen adapter.

## 7. Feature lifecycle testing

- Valid package discovery and registration.
- Manifest JSON Schema validation, unknown fields, malformed dependencies, and path traversal.
- Deterministic digest verification, untrusted packages, and post-registration tampering.
- ZIP path traversal, symlink, file-count, expanded-size, and atomic installation behavior.
- Invalid manifest rejection.
- Missing/incompatible feature and service dependency rejection, including dependency-cycle detection.
- Enable and disable behavior.
- Unauthorized feature execution rejection.
- Update validation, data-schema migration rejection, backup retention, and failed-update rollback.
- Uninstall blocked while jobs are active.
- Registry lifecycle operations recorded in audit history.
- Feature catalog excludes disabled, tampered, dependency-incomplete, unlicensed, and unauthorized features.
- Service dependency versions support exact and documented wildcard selectors.

## 8. GUI testing

- Set `QT_QPA_PLATFORM=offscreen` for automated GUI tests in headless environments.
- Reuse a single `QApplication` instance across tests.
- Verify static page navigation and active navigation state.
- Verify dashboard cards and sidebar feature entries come only from the injected feature catalog.
- Verify an unknown or no-longer-authorized feature ID cannot be opened from a stale UI action.
- Verify feature workspaces are created lazily through the presentation adapter and reused.
- Verify unavailable Feature Manager or workspace adapters produce an explicit state rather than
  simulated lifecycle actions or fabricated feature entries.
- Manually inspect minimum window sizing, page clipping, navigation selection, and error states
  on the supported Windows desktop environment.

## 9. Test data and privacy

- Do not commit customer documents, credentials, production databases, or sensitive OCR output.
- Prefer synthetic fixtures and fake/in-memory services for unit tests.
- Keep test fixtures minimal and documented.
- Redact sensitive values from logs and test reports.

## 10. Stage 5 automated test scope

Stage 5 tests are located in `tests/unit/feature_manager/` and cover manifest parsing,
package integrity, safe installation, lifecycle policy, SQLite persistence/audit, authorization
projection, and install/update/disable/uninstall workflows. The Service Registry wildcard
compatibility behavior is covered by `tests/unit/test_service_registry.py`.

The Stage 5 baseline originally used deny-all authorization. Stage 6 replaces that production
bootstrap adapter with persisted RBAC authorization while retaining deny-all behavior as a safe
test/deployment fallback. The trusted package digest allowlist remains empty; tests inject explicit
fake authorization and trusted digests, and production configuration must not weaken fail-closed defaults.

## 11. Test execution policy

The exact test runner and commands will be documented after the Python toolchain and dependency baseline are approved. Do not claim tests passed unless they were actually executed and the results recorded.

## 12. Definition of Done

A change is ready when applicable unit, contract, integration, regression, security, and GUI tests have been run; failures are resolved or explicitly documented; and relevant contracts and documentation are updated.


## 13. Stage 6 authentication and authorization tests

- First-run Administrator setup succeeds once and cannot be repeated.
- Password hashes use unique salts; correct passwords verify and incorrect passwords fail.
- Password policy rejects values shorter than 12 characters or longer than 128 characters.
- Login errors do not disclose whether a username exists.
- Five consecutive invalid attempts lock an account for 15 minutes; locked and inactive users cannot sign in.
- Successful login resets the failed-attempt counter and records a security audit event.
- RBAC supports exact, namespace wildcard, and global permissions; missing/unknown users are denied.
- User creation, role assignment, and account activation/deactivation require `user.manage`.
- A user cannot deactivate their own account or remove/deactivate the last active Administrator.
- Sessions expire after 30 minutes idle or 12 hours absolute and can be explicitly revoked.
- Feature Manager mutations remain denied when the actor lacks the required permission, including
  when called without the GUI.
- UI pages are hidden for usability when permissions are absent, but service-boundary checks remain
  the authoritative control.


## 14. Stage 7 runtime and workspace tests

- Activation rejects a feature that is not enabled or whose requesting user lacks
  `feature.view.<feature_id>`.
- Activation rechecks package integrity, declared feature/service dependencies, and
  license entitlement before importing feature code.
- Feature contexts can resolve only service IDs declared in the feature manifest;
  undeclared lookups are rejected.
- Entry-point and workspace module targets must resolve inside the verified package;
  symlinks escaping the package root are rejected.
- The feature descriptor must exactly match the verified manifest.
- Relative imports work under the feature-specific module namespace without adding the
  package directory to global `sys.path`.
- Repeated activation reuses the initialized instance; workspace instances must match
  the manifest-declared workspace class.
- Failed initialization calls `shutdown()` when available and removes partially loaded
  modules.
- Disable, update, uninstall, and application shutdown unload feature instances and
  dispose their presentation workspaces.
- The presentation adapter rejects a workspace that is not a PySide6 `QWidget`.
- Verify the application GUI manually on Windows with an enabled, trusted test feature;
  the default bootstrap trust allowlist is intentionally empty.


## 15. Stage 12 Excel adapter test scope

The Excel adapter unit tests use generated workbooks and do not require customer files.
They cover workbook inspection, worksheet enumeration, header-based reads, preservation
of text identifiers/leading zeroes, mapping-based key matching, duplicate-key rejection,
unmatched-key failure, overwrite behavior, formula preservation, formula-like input
literalization, source immutability, corrupt workbook verification, and Service Registry
registration. Add representative `.xlsm`, pivot-table, chart, image, external-link, and
large-workbook fixtures before declaring those features production-compatible.


## 16. Stage 13.7 Tax Invoice integration and workflow hardening

Run the deterministic integration coverage with:

```powershell
uv run pytest -q tests/integration/test_tax_invoice_workflow.py features/tax_invoice/tests tests/unit/services/excel/test_openpyxl_adapter.py
```

The Stage 13.7 workflow tests must verify:

- A mixed batch containing one successful document, one review document, and one failed document returns three distinct per-file outcomes and consistent aggregate counts.
- Only the successful document is passed to the Excel write operation.
- The original workbook remains byte-for-byte unchanged; the separate output workbook contains the successful mapped value.
- A successful extraction with zero matching/writable Excel rows is changed to internal `review` (GUI label **Need Review**) and does not report an output path.
- An unexpected Excel adapter exception is contained at the feature boundary and marks affected successful documents `failed` with `TAX_INVOICE_EXCEL_OUTPUT_FAILED`; implementation details remain in protected logs.
- A failure in one PDF does not abort processing of the remaining PDFs in a batch.
- Internal `skipped` results, if surfaced, are grouped with **Need Review** in the GUI summary and table.

The automated integration tests use synthetic document outcomes and a real temporary `.xlsx`
workbook. They do not validate actual Tesseract language-pack availability, Windows filesystem
permissions, or PySide6 event-loop behavior. Run the complete suite and manually exercise the
workspace on the pinned Python 3.12 + PySide6 Windows environment before release.


## 17. Standard Python 3.12 + PySide6 environment

The supported desktop and CI validation runtime is Python 3.12.x on Windows with the
project dependencies installed from `pyproject.toml` and `uv.lock`. The `.python-version`
file pins the interpreter line. Keep `uv.lock` committed and synchronized with project
metadata; dependency changes must include the refreshed lockfile.

### Local Windows setup

Install `uv`, then run from the repository root in PowerShell:

```powershell
.\scripts\setup_test_environment.ps1
```

The setup script installs Python 3.12 through uv, resolves and checks the lockfile, installs
all dependency groups, and verifies PySide6 plus Qt's offscreen platform. The first setup
may update `uv.lock`; review and commit that file with the dependency metadata change.

### Local full validation

```powershell
.\scripts\run_all_tests.ps1
```

For GUI-focused tests only:

```powershell
.\scripts\run_gui_tests.ps1
```

Automated GUI tests set `QT_QPA_PLATFORM=offscreen`. They verify Qt widget construction and
interaction logic without requiring a visible desktop. They do not replace manual visual
inspection on a supported Windows desktop.

### GitHub Actions

`.github/workflows/windows-python312-tests.yml` runs on pushes and pull requests targeting
`main` or `master`, and can also be started manually. It resolves/checks the dependency lock,
installs the locked environment, verifies Python/PySide6/Qt, runs Ruff, compiles source files,
and runs the complete pytest suite. A JUnit XML test report and the resolved `uv.lock` are
uploaded as workflow artifacts.

On the first CI run after importing an older repository, the workflow may refresh a stale
`uv.lock`. Download the `uv-lockfile-windows-python312` artifact and commit its contents to
the repository. Subsequent runs should leave the committed lockfile unchanged. Never commit
virtual environments, caches, generated reports, customer documents, or secrets.

### Environment verification contract

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
uv run python scripts/verify_environment.py --require-pyside6 --require-qt-offscreen
```

The verifier fails unless Python is 3.12.x, all declared runtime/development distributions
are installed, PySide6 imports, and a basic Qt widget can be created in offscreen mode.
Tesseract executable and language-pack availability are intentionally not asserted by this
check; OCR adapter unit tests should mock the engine boundary, while a separate real-engine
smoke test must be run on a machine provisioned with the approved Tesseract installation
and Indonesian/English language data.

### CI acceptance policy

- Do not exclude GUI/bootstrap tests in the supported Windows CI job.
- Do not use `continue-on-error` for lint, compile, environment, or test steps.
- A skipped test must have an explicit reason; unexpected skips are release blockers.
- Attach the JUnit report and preserve the workflow run URL in the stage validation record.
- Manual Windows visual checks and real Tesseract checks remain separately recorded acceptance items.
