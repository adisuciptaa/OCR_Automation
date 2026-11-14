"""SQLite persistence adapter for feature-scoped configuration profiles."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.core.exceptions import ApplicationError
from app.feature_manager.models import ConfigurationScope, FeatureConfiguration


class SQLiteFeatureConfigurationRepository:
    def __init__(self, database_path: Path | str, migration_path: Path | None = None) -> None:
        self._path = Path(database_path)
        self._migration_path = migration_path or Path(__file__).parents[1] / "migrations" / "0003_feature_configuration.sql"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(self._migration_path.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def get(self, feature_id: str, scope: ConfigurationScope, scope_key: str) -> FeatureConfiguration | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM feature_configuration_profiles WHERE feature_id=? AND scope=? AND scope_key=?",
                (feature_id, scope.value, scope_key),
            ).fetchone()
        return self._from_row(row) if row else None

    def save(self, configuration: FeatureConfiguration) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO feature_configuration_profiles
                (feature_id, scope, scope_key, schema_version, configuration_json, created_at, updated_at, updated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(feature_id, scope, scope_key) DO UPDATE SET
                schema_version=excluded.schema_version, configuration_json=excluded.configuration_json,
                updated_at=excluded.updated_at, updated_by=excluded.updated_by""",
                (configuration.feature_id, configuration.scope.value, configuration.scope_key,
                 configuration.schema_version, json.dumps(dict(configuration.values), ensure_ascii=False, sort_keys=True),
                 configuration.created_at.isoformat(), configuration.updated_at.isoformat(), configuration.updated_by),
            )

    def delete(self, feature_id: str, scope: ConfigurationScope, scope_key: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "DELETE FROM feature_configuration_profiles WHERE feature_id=? AND scope=? AND scope_key=?",
                (feature_id, scope.value, scope_key),
            )

    def list_for_feature(self, feature_id: str) -> tuple[FeatureConfiguration, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM feature_configuration_profiles WHERE feature_id=? ORDER BY scope, scope_key",
                (feature_id,),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)


    def migrate_profiles(self, feature_id: str, updates: list[tuple[ConfigurationScope, str, int, dict[str, object]]], actor_id: str) -> None:
        """Atomically update all selected profile payloads and schema versions."""
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection, connection:
            for scope, scope_key, schema_version, values in updates:
                cursor = connection.execute(
                    "UPDATE feature_configuration_profiles SET schema_version=?, configuration_json=?, updated_at=?, updated_by=? "
                    "WHERE feature_id=? AND scope=? AND scope_key=?",
                    (schema_version, json.dumps(values, ensure_ascii=False, sort_keys=True), now, actor_id,
                     feature_id, getattr(scope, "value", str(scope)), scope_key),
                )
                if cursor.rowcount != 1:
                    raise ApplicationError("FEATURE_CONFIGURATION_CONCURRENT_MODIFICATION",
                        "A configuration profile changed while migration was being applied.")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> FeatureConfiguration:
        return FeatureConfiguration(
            feature_id=row["feature_id"], scope=ConfigurationScope(row["scope"]), scope_key=row["scope_key"],
            schema_version=int(row["schema_version"]), values=json.loads(row["configuration_json"]),
            created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
            updated_by=row["updated_by"],
        )
