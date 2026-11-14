# Tax Invoice Reader

Business Feature Module for detecting Indonesian tax invoice pages and extracting the tax
invoice number and its related invoice number.

## Stage 13.1 — Contract baseline

Implemented public models and contracts:

- `models.TaxInvoiceFieldValue`: preserves raw and normalized values separately and records
  source page and engine-specific confidence semantics.
- `models.TaxInvoicePageDetection`: records page-level candidate decisions, search region,
  matched markers, reason codes, and fallback use.
- `models.TaxInvoiceExtraction`: immutable per-document extraction outcome.
- `contracts.TaxInvoiceFeatureContract`: typed feature lifecycle contract using the
  application-level `JobRequest` and `JobResult`.

The MVP identifier scope is `tax_invoice_number` and `invoice_number`.

## Stage 13.2 — Manifest and configuration

- `manifest.json` declares feature identity/version, entry point, API contract compatibility,
  permissions, license entitlement, workspace target, and versioned Shared Service dependencies.
- `config_schema.json` is the authoritative configuration schema consumed by the existing
  Feature Configuration Manager. Its independent `x-config-version` remains `1`; Stage 13.3 added an optional render DPI key with a backward-compatible default.
- `config.py` exposes a fresh default configuration mapping for feature-owned code.
- `entry.py` supplies the manifest-declared lifecycle entry point, validates configuration,
  resolves declared PDF/OCR services, and adapts per-file outcomes to `JobResult`.
- `ui.py` is a manifest target placeholder; it is not yet a PySide6 QWidget and must not be
  presented as a usable workspace before Stage 13.6.

Configuration defaults:

| Group | Setting | Default |
|---|---|---:|
| Detection | Top region ratio | 0.25 |
| Detection | Marker phrases | `FAKTUR PAJAK`, `FAKTURPAJAK` |
| Detection | Full-page fallback | Disabled |
| OCR | Prefer embedded PDF text | Enabled |
| OCR | Language | `ind+eng` |
| Processing | Maximum pages per document | 200 |
| Processing | PDF render DPI | 200 |

The OCR adapter remains authoritative for checking whether the requested traineddata is
available. No universal confidence threshold is configured because engine confidence scales
are not interchangeable.

The package manifest is metadata, not a signature. Package authenticity continues to be
controlled by the existing publisher trust and package-signature verification flow. The
repository does not claim this development ZIP is signed or production-installable.

## Stage 13.3 — Detection and extraction

- `detector.py` performs marker matching with punctuation/spacing-insensitive comparison.
- `extractor.py` inspects PDFs, enforces page limits, prefers embedded text when configured,
  runs OCR over the configured top region for scanned pages, and uses full-page fallback only
  when enabled.
- Candidate pages are OCRed at full-page resolution when embedded text is unavailable.
- The current MVP captures only `tax_invoice_number` and `invoice_number`, preserving raw
  values, source page, and engine-specific OCR confidence. Normalized values remain unset
  until Stage 13.4.
- Missing markers or fields produce a manual-review outcome. Per-file application failures
  are isolated and represented with stable error codes.
- Embedded PDF text has no positional geometry in the current public PDF contract; marker
  detection on that path is page-wide rather than a verified top-region-only match.

## Stage 13.4 — Normalization and validation

- `normalizer.py` canonicalizes accepted 16-digit tax invoice numbers to
  `000.000-00.00000000`; it does not guess OCR substitutions or missing digits.
- Invoice numbers receive conservative Unicode NFKC and whitespace normalization only;
  case and punctuation are retained.
- `validator.py` assigns `valid`, `invalid`, `missing`, or `conflict` at field level.
- Repeated equivalent values across candidate pages are accepted; distinct normalized
  values for the same field are marked as conflicts and require manual review.
- Raw values and OCR confidence remain preserved. Normalized values are populated only
  when validation succeeds. The per-file result includes a validation summary.
- A document is successful only when both MVP identifiers validate; otherwise it is marked
  for review. This is a format/consistency check, not an external tax-authority verification.

## Remaining stages

- Stage 13.4: completed — identifier normalization and business validation.
- Stage 13.5: configured Excel mapping and safe output.
- Stage 13.6: PySide6 feature workspace.
- Stage 13.7: integration and end-to-end tests.


## Stage 13.5 — Excel Mapping + Output

Excel output is activated by supplying an `excel` object in the feature configuration.
Configure the source workbook path, worksheet, header/data rows, source key and target
columns, match/write fields, and duplicate/unmatched/overwrite policies. The `JobRequest.output_path`
is the destination workbook path; it must differ from the source workbook.

Only `success` file results are eligible for Excel mapping. `review` (user-facing label
**Need Review**), `failed`, and `skipped` results are excluded before the Excel service is
called. If a success result is missing a required normalized identifier, it is changed to
`review` and excluded. If there are no eligible records, no output workbook is created.

For invoice-number keys, use `remove_whitespace` to remove all whitespace from workbook
keys before matching; this mirrors the feature's invoice normalized-value behavior. The
original workbook is preserved and the verified output is written to a separate destination.


## Stage 13.6 GUI Workspace

The PySide6 workspace supports multiple PDF inputs, configurable detection/OCR settings,
optional Excel source/mapping/output settings, background execution, summary counts, and
per-file result details. User-facing statuses are Success, Need Review, and Failed. The
internal `review` value is preserved in `JobResult`; only `success` is eligible for Excel output.
