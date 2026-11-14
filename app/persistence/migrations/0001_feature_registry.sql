CREATE TABLE IF NOT EXISTS feature_registry (
    feature_id TEXT PRIMARY KEY,
    manifest_json TEXT NOT NULL,
    package_path TEXT NOT NULL,
    package_digest TEXT NOT NULL,
    signature_status TEXT NOT NULL,
    state TEXT NOT NULL,
    installed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_error_code TEXT
);

CREATE TABLE IF NOT EXISTS feature_audit (
    audit_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    feature_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    previous_state TEXT,
    resulting_state TEXT,
    package_digest TEXT,
    result TEXT NOT NULL,
    error_code TEXT,
    occurred_at TEXT NOT NULL
);
