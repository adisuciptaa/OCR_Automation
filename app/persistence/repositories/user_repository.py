"""SQLite persistence adapter for users, RBAC assignments, and security audit."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.security.models import AuthUserRecord, RoleSummary, UserIdentity, UserSummary


class SQLiteUserRepository:
    def __init__(self, database_path: Path | str, migration_path: Path | None = None) -> None:
        self._path = Path(database_path)
        self._migration_path = migration_path or Path(__file__).parents[1] / "migrations" / "0002_authentication.sql"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(self._migration_path.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def has_users(self) -> bool:
        with closing(self._connect()) as connection:
            return connection.execute("SELECT 1 FROM app_users LIMIT 1").fetchone() is not None

    def create_initial_admin(self, username: str, display_name: str, password_hash: str) -> UserIdentity:
        now = datetime.now(UTC).isoformat()
        user_id = str(uuid4())
        with closing(self._connect()) as connection, connection:
            if connection.execute("SELECT 1 FROM app_users LIMIT 1").fetchone():
                raise ValueError("Initial administrator has already been created.")
            connection.execute(
                "INSERT INTO app_users(user_id, username, display_name, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, username, display_name, password_hash, now, now),
            )
            connection.execute("INSERT INTO app_user_roles(user_id, role_id) VALUES (?, 'administrator')", (user_id,))
        identity = self.get_identity(user_id)
        if identity is None:
            raise RuntimeError("Created administrator could not be reloaded.")
        return identity

    def create_user(self, username: str, display_name: str, password_hash: str, role_ids: tuple[str, ...]) -> UserIdentity:
        now, user_id = datetime.now(UTC).isoformat(), str(uuid4())
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO app_users(user_id, username, display_name, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, username, display_name, password_hash, now, now),
            )
            for role_id in role_ids:
                connection.execute("INSERT INTO app_user_roles(user_id, role_id) VALUES (?, ?)", (user_id, role_id))
        identity = self.get_identity(user_id)
        if identity is None:
            raise RuntimeError("Created user could not be reloaded.")
        return identity

    def get_auth_record(self, username: str) -> AuthUserRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM app_users WHERE username = ? COLLATE NOCASE", (username,)
            ).fetchone()
        if row is None:
            return None
        return AuthUserRecord(
            row["user_id"], row["username"], row["password_hash"], bool(row["is_active"]),
            int(row["failed_login_attempts"]),
            datetime.fromisoformat(row["locked_until"]) if row["locked_until"] else None,
        )

    def get_identity(self, user_id: str) -> UserIdentity | None:
        with closing(self._connect()) as connection:
            user = connection.execute("SELECT * FROM app_users WHERE user_id = ?", (user_id,)).fetchone()
            if user is None:
                return None
            roles = tuple(row[0] for row in connection.execute(
                "SELECT r.name FROM app_roles r JOIN app_user_roles ur ON ur.role_id=r.role_id WHERE ur.user_id=? ORDER BY r.name", (user_id,)
            ).fetchall())
            permissions = tuple(row[0] for row in connection.execute(
                "SELECT DISTINCT rp.permission_id FROM app_role_permissions rp JOIN app_user_roles ur ON ur.role_id=rp.role_id WHERE ur.user_id=? ORDER BY rp.permission_id", (user_id,)
            ).fetchall())
        return UserIdentity(user["user_id"], user["username"], user["display_name"], bool(user["is_active"]), roles, permissions)

    def is_active(self, user_id: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT is_active FROM app_users WHERE user_id=?", (user_id,)).fetchone()
        return bool(row and row[0])

    def user_has_permission(self, user_id: str, permission: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT 1 FROM app_users u
                JOIN app_user_roles ur ON ur.user_id=u.user_id
                JOIN app_role_permissions rp ON rp.role_id=ur.role_id
                WHERE u.user_id=? AND u.is_active=1 AND
                (rp.permission_id='*' OR rp.permission_id=? OR
                 (rp.permission_id LIKE '%.*' AND ? LIKE substr(rp.permission_id, 1, length(rp.permission_id)-1) || '%'))
                LIMIT 1""", (user_id, permission, permission)
            ).fetchone()
        return row is not None

    def record_failed_login(self, user_id: str | None, *, locked_until: datetime | None) -> None:
        with closing(self._connect()) as connection, connection:
            if user_id:
                connection.execute(
                    "UPDATE app_users SET failed_login_attempts=failed_login_attempts+1, locked_until=?, updated_at=? WHERE user_id=?",
                    (locked_until.isoformat() if locked_until else None, datetime.now(UTC).isoformat(), user_id),
                )

    def reset_login_failures(self, user_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute("UPDATE app_users SET failed_login_attempts=0, locked_until=NULL, last_login_at=?, updated_at=? WHERE user_id=?",
                               (now, now, user_id))

    def audit(self, *, actor_id: str | None, action: str, target_user_id: str | None,
              outcome: str, error_code: str | None = None, details: dict[str, object] | None = None) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO security_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid4()), actor_id, action, target_user_id, outcome, error_code,
                 datetime.now(UTC).isoformat(), json.dumps(details or {}, ensure_ascii=False)),
            )

    def list_users(self) -> tuple[UserSummary, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM app_users ORDER BY username COLLATE NOCASE").fetchall()
            results = []
            for row in rows:
                roles = tuple(item[0] for item in connection.execute(
                    "SELECT r.name FROM app_roles r JOIN app_user_roles ur ON ur.role_id=r.role_id WHERE ur.user_id=? ORDER BY r.name", (row["user_id"],)
                ).fetchall())
                results.append(UserSummary(row["user_id"], row["username"], row["display_name"],
                    bool(row["is_active"]), roles, datetime.fromisoformat(row["created_at"]),
                    datetime.fromisoformat(row["last_login_at"]) if row["last_login_at"] else None))
        return tuple(results)

    def list_roles(self) -> tuple[RoleSummary, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM app_roles ORDER BY name").fetchall()
        return tuple(RoleSummary(row["role_id"], row["name"], row["description"], bool(row["is_system"])) for row in rows)


    def get_user_role_ids(self, user_id: str) -> tuple[str, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT role_id FROM app_user_roles WHERE user_id=? ORDER BY role_id", (user_id,)
            ).fetchall()
        return tuple(row[0] for row in rows)

    def update_user_roles(self, user_id: str, role_ids: tuple[str, ...]) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM app_user_roles WHERE user_id=?", (user_id,))
            for role_id in role_ids:
                connection.execute("INSERT INTO app_user_roles(user_id, role_id) VALUES (?, ?)", (user_id, role_id))


    def has_global_admin_permission(self, user_id: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT 1 FROM app_users u JOIN app_user_roles ur ON ur.user_id=u.user_id
                JOIN app_role_permissions rp ON rp.role_id=ur.role_id
                WHERE u.user_id=? AND u.is_active=1 AND rp.permission_id='*' LIMIT 1""", (user_id,)
            ).fetchone()
        return row is not None

    def count_active_global_administrators(self) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT COUNT(DISTINCT u.user_id) FROM app_users u
                JOIN app_user_roles ur ON ur.user_id=u.user_id
                JOIN app_role_permissions rp ON rp.role_id=ur.role_id
                WHERE u.is_active=1 AND rp.permission_id='*'"""
            ).fetchone()
        return int(row[0])

    def role_ids_have_global_permission(self, role_ids: tuple[str, ...]) -> bool:
        if not role_ids:
            return False
        placeholders = ",".join("?" for _ in role_ids)
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"SELECT 1 FROM app_role_permissions WHERE permission_id='*' AND role_id IN ({placeholders}) LIMIT 1",
                role_ids,
            ).fetchone()
        return row is not None

    def set_user_active(self, user_id: str, is_active: bool) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("UPDATE app_users SET is_active=?, updated_at=? WHERE user_id=?",
                               (int(is_active), datetime.now(UTC).isoformat(), user_id))
