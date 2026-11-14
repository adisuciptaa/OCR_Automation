CREATE TABLE IF NOT EXISTS app_users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS app_roles (
    role_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT NOT NULL,
    is_system INTEGER NOT NULL DEFAULT 0 CHECK (is_system IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_permissions (
    permission_id TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_user_roles (
    user_id TEXT NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    role_id TEXT NOT NULL REFERENCES app_roles(role_id) ON DELETE RESTRICT,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS app_role_permissions (
    role_id TEXT NOT NULL REFERENCES app_roles(role_id) ON DELETE CASCADE,
    permission_id TEXT NOT NULL REFERENCES app_permissions(permission_id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS security_audit (
    audit_id TEXT PRIMARY KEY,
    actor_id TEXT,
    action TEXT NOT NULL,
    target_user_id TEXT,
    outcome TEXT NOT NULL,
    error_code TEXT,
    occurred_at TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_app_users_username ON app_users(username);
CREATE INDEX IF NOT EXISTS idx_security_audit_occurred_at ON security_audit(occurred_at);

INSERT OR IGNORE INTO app_roles (role_id, name, description, is_system, created_at)
VALUES
    ('administrator', 'Administrator', 'Full application administration access.', 1, '2026-11-12T00:00:00+00:00'),
    ('operator', 'Operator', 'Can use permitted document-processing features.', 1, '2026-11-12T00:00:00+00:00'),
    ('viewer', 'Viewer', 'Read-only access to permitted information.', 1, '2026-11-12T00:00:00+00:00');

INSERT OR IGNORE INTO app_permissions (permission_id, description) VALUES
    ('*', 'All application permissions.'),
    ('job.execute', 'Execute document-processing jobs.'),
    ('job.cancel', 'Cancel document-processing jobs.'),
    ('job.view_own', 'View own processing jobs.'),
    ('job.view_all', 'View all processing jobs.'),
    ('feature.view.*', 'View enabled business features.'),
    ('feature.registry.view', 'View installed Feature Registry records.'),
    ('feature.configure.*', 'Configure business features.'),
    ('feature.install', 'Install and register feature packages.'),
    ('feature.update', 'Update feature packages.'),
    ('feature.uninstall', 'Uninstall feature packages.'),
    ('user.manage', 'Manage application users and role assignments.'),
    ('role.manage', 'Manage roles and permission assignments.'),
    ('audit.view', 'View security and application audit records.'),
    ('settings.manage', 'Manage application settings.');

INSERT OR IGNORE INTO app_role_permissions (role_id, permission_id)
SELECT 'administrator', permission_id FROM app_permissions WHERE permission_id = '*';
INSERT OR IGNORE INTO app_role_permissions (role_id, permission_id)
VALUES
    ('operator', 'job.execute'), ('operator', 'job.cancel'),
    ('operator', 'job.view_own'), ('operator', 'feature.view.*'),
    ('viewer', 'job.view_own'), ('viewer', 'feature.view.*');

INSERT OR IGNORE INTO app_permissions (permission_id, description)
VALUES ('publisher.manage', 'Register, rotate, and revoke trusted feature publishers.');
