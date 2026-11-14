CREATE TABLE IF NOT EXISTS publisher_registry (
    publisher_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS publisher_keys (
    publisher_id TEXT NOT NULL REFERENCES publisher_registry(publisher_id) ON DELETE RESTRICT,
    key_id TEXT NOT NULL,
    public_key_b64 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    PRIMARY KEY (publisher_id, key_id)
);

CREATE TABLE IF NOT EXISTS publisher_trust_audit (
    audit_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    publisher_id TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_publisher_keys_status ON publisher_keys(publisher_id, status);
CREATE INDEX IF NOT EXISTS idx_publisher_audit_time ON publisher_trust_audit(occurred_at);
