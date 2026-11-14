"""SQLite persistence adapter for Feature Registry and lifecycle audit."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.feature_manager.models import (
    FeatureDependencies, FeatureDependency, FeatureManifest, FeatureRecord, FeatureState, ServiceDependency,
)


class SQLiteFeatureRegistryRepository:
    def __init__(self, database_path: Path | str, migration_path: Path | None = None) -> None:
        self._path = Path(database_path)
        self._migration_path = migration_path or Path(__file__).parents[1] / "migrations" / "0001_feature_registry.sql"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(self._migration_path.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def get(self, feature_id: str) -> FeatureRecord | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute("SELECT * FROM feature_registry WHERE feature_id=?", (feature_id,)).fetchone()
        return self._from_row(row) if row else None

    def list_all(self) -> tuple[FeatureRecord, ...]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute("SELECT * FROM feature_registry ORDER BY feature_id").fetchall()
        return tuple(self._from_row(row) for row in rows)

    def save(self, record: FeatureRecord) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """INSERT INTO feature_registry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(feature_id) DO UPDATE SET manifest_json=excluded.manifest_json,
                package_path=excluded.package_path, package_digest=excluded.package_digest,
                signature_status=excluded.signature_status, state=excluded.state,
                installed_at=excluded.installed_at, updated_at=excluded.updated_at,
                last_error_code=excluded.last_error_code""",
                (record.feature_id, json.dumps(dict(record.manifest.raw), ensure_ascii=False),
                 record.package_path, record.package_digest, record.signature_status,
                 record.state.value, record.installed_at.isoformat(), record.updated_at.isoformat(),
                 record.last_error_code),
            )

    def delete(self, feature_id: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM feature_registry WHERE feature_id=?", (feature_id,))

    def audit(self, *, actor_id: str, feature_id: str, operation: str,
              previous_state: str | None, resulting_state: str | None,
              package_digest: str | None, result: str, error_code: str | None = None) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO feature_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid4()), actor_id, feature_id, operation, previous_state, resulting_state,
                 package_digest, result, error_code, datetime.now(UTC).isoformat()),
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> FeatureRecord:
        raw = json.loads(row["manifest_json"])
        deps = raw["dependencies"]
        manifest = FeatureManifest(
            manifest_schema_version=raw["manifest_schema_version"], feature_id=raw["feature_id"],
            display_name=raw["display_name"], version=raw["version"], description=raw["description"],
            publisher=raw["publisher"], entry_point=raw["entry_point"],
            minimum_core_version=raw["minimum_core_version"], maximum_core_version=raw.get("maximum_core_version"),
            api_contract_version=raw["api_contract_version"],
            dependencies=FeatureDependencies(tuple(
                FeatureDependency(item["id"], item["version"]) for item in deps["features"]), tuple(
                ServiceDependency(item["id"], item["version"]) for item in deps["services"])),
            permissions=tuple(raw["permissions"]), configuration_schema=raw["configuration_schema"],
            navigation_label=raw["ui"]["navigation_label"], icon=raw["ui"]["icon"],
            workspace=raw["ui"]["workspace"], license_entitlement=raw.get("license_entitlement"),
            data_schema_version=raw["data_schema_version"], raw=raw,
            publisher_id=raw.get("publisher_id"),
        )
        return FeatureRecord(manifest, row["package_path"], row["package_digest"],
            row["signature_status"], FeatureState(row["state"]),
            datetime.fromisoformat(row["installed_at"]), datetime.fromisoformat(row["updated_at"]),
            row["last_error_code"])
