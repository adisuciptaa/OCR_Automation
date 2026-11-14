# Feature Migration Guide

This guide defines the migration asset format introduced in Stage 8.3. Migration assets
belong to the feature package and are executed by the Core-owned
`FeatureDataMigrationEngine`; they are not loaded as Python modules.

## 1. Version streams

Keep these version streams independent:

- `x-config-version` in `config_schema.json`: version of persisted configuration profiles.
- `data_schema_version` in `manifest.json`: version of the feature-owned SQLite data model.

Use positive integers. Provide every intermediate version step; migrations are sequential
and are not inferred from package version numbers.

## 2. Configuration migration

Path: `migrations/configuration/NNNN_to_NNNN.json`

Example `0001_to_0002.json`:

```json
{
  "from_version": 1,
  "to_version": 2,
  "operations": [
    {"op": "rename_field", "field": "invoice_number", "to": "document_number"},
    {"op": "remove_field", "field": "legacy_mode"},
    {"op": "set_default", "field": "language", "value": "id"},
    {"op": "map_value", "field": "layout", "mapping": {"old": "standard"}}
  ]
}
```

Supported operations:

- `rename_field`: rename a field only when the destination does not already exist.
- `remove_field`: remove a deprecated field.
- `set_default`: add a value only when the field is absent.
- `map_value`: replace an existing value when it appears in the supplied mapping.

All stored profiles are migrated and validated against the target schema before the
repository commits the profile updates in one transaction. If any profile cannot be
migrated or validated, no profile is changed.

## 3. Feature data migration

Path: `migrations/data/NNNN_to_NNNN.sql`

Example `0001_to_0002.sql`:

```sql
ALTER TABLE extracted_documents ADD COLUMN source_page INTEGER;
CREATE INDEX idx_extracted_documents_source_page
    ON extracted_documents(source_page);
```

Scripts execute against the feature's isolated SQLite database. The engine owns the
transaction boundary, checks the stored version in `feature_data_schema`, and records
applied steps in `feature_migration_history`.
Do not include `BEGIN`, `COMMIT`, `ROLLBACK`, `SAVEPOINT`, `RELEASE`, `ATTACH`, `DETACH`,
`PRAGMA`, `VACUUM`, or extension-loading statements. Do not rely on external database
connections, filesystem commands, or network access.

## 4. Security and review

- Migration package roots must be verified against the external trusted digest allowlist.
- Symlinks, path escapes, unexpected migration file names, duplicate steps, and version
  gaps are rejected.
- SQL migration files are executable changes to persistent data. Review them as carefully
  as application code and test them against representative prior-version databases.
- Never log configuration values, OCR contents, credentials, or customer data.
- A successful data migration retains a pre-migration SQLite backup. Failed SQL runs are
  rolled back by SQLite transaction handling.

## 5. Current limitation

Stage 8.3 provides migration execution services. Automatic feature package updates that
change `data_schema_version` remain blocked until Stage 8.4 coordinates package health
checks and rollback across package files, configuration profiles, and feature data.
