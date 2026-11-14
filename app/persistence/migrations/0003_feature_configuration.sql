CREATE TABLE IF NOT EXISTS feature_configuration_profiles (
    feature_id TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('installation', 'company', 'user', 'job')),
    scope_key TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
    configuration_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    PRIMARY KEY (feature_id, scope, scope_key)
);

CREATE INDEX IF NOT EXISTS idx_feature_configuration_feature
ON feature_configuration_profiles(feature_id);
