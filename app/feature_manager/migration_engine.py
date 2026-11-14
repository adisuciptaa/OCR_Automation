"""Controlled, versioned feature configuration and SQLite data migrations.

Migration files are declarative JSON for configuration and reviewed SQL for feature-owned
SQLite data. Only verified installed/candidate package roots may be supplied by callers.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.event_bus import ApplicationEvent, EventBus
from app.core.exceptions import ApplicationError
from app.feature_manager.contracts import AuthorizationService, FeatureConfigurationRepository, FeatureRegistryRepository
from app.feature_manager.configuration_manager import FeatureConfigurationManagerService
from app.feature_manager.models import ConfigurationScope, FeatureManifest
from app.feature_manager.manifest_loader import ManifestLoader
from app.feature_manager.package_verifier import PackageVerifier

_MIGRATION_NAME = re.compile(r"^(?P<source>[0-9]{4})_to_(?P<target>[0-9]{4})\.(?P<kind>json|sql)$")
_FORBIDDEN_SQL = re.compile(r"\b(BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE|ATTACH|DETACH|VACUUM|PRAGMA|LOAD_EXTENSION)\b", re.I)


class FeatureDataMigrationEngine:
    """Executes ordered, auditable migrations without silently coercing feature data."""

    def __init__(self, *, configurations: FeatureConfigurationRepository,
                 authorization: AuthorizationService, registry: FeatureRegistryRepository,
                 data_root: Path, backup_root: Path, verifier: PackageVerifier,
                 event_bus: EventBus | None = None,
                 logger: logging.Logger | None = None) -> None:
        self._configurations = configurations
        self._authorization = authorization
        self._registry = registry
        self._data_root = Path(data_root).resolve()
        self._backup_root = Path(backup_root).resolve()
        self._verifier = verifier
        self._event_bus = event_bus
        self._logger = logger or logging.getLogger(__name__)

    def migrate_configuration_profiles(self, *, feature_id: str, actor_id: str,
                                       package_root: Path, target_version: int) -> int:
        """Migrate every stored profile to target_version in one repository transaction."""
        self._authorization.require(actor_id, f"feature.configure.{feature_id}", {"feature_id": feature_id})
        root, manifest, package_digest = self._load_verified_manifest(feature_id, package_root)
        migration_dir = self._safe_child(root, "migrations/configuration")
        if migration_dir.exists() and not migration_dir.is_dir():
            raise ApplicationError("FEATURE_MIGRATION_PATH_INVALID", "Configuration migration path must be a directory.")
        schema_path = self._safe_child(root, manifest.configuration_schema)
        try:
            schema_definition = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Target configuration schema cannot be read.") from exc
        if not isinstance(schema_definition, dict) or schema_definition.get("type") != "object":
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Target configuration schema must define an object root.")
        FeatureConfigurationManagerService._validate_schema_definition(schema_definition)
        if FeatureConfigurationManagerService._schema_version(schema_definition) != target_version:
            raise ApplicationError("FEATURE_MIGRATION_VERSION_INVALID", "Target schema version does not match target_version.")
        profiles = self._configurations.list_for_feature(feature_id)
        if not profiles:
            return 0
        migrations = self._load_configuration_migrations(migration_dir)
        updates: list[tuple[ConfigurationScope, str, int, dict[str, Any]]] = []
        for profile in profiles:
            if profile.schema_version > target_version:
                raise ApplicationError("FEATURE_MIGRATION_DOWNGRADE_UNSUPPORTED",
                    "Stored configuration is newer than the target schema.")
            version = profile.schema_version
            values = dict(profile.values)
            while version < target_version:
                migration = migrations.get(version)
                if migration is None:
                    raise ApplicationError("FEATURE_CONFIGURATION_MIGRATION_MISSING",
                        "A required configuration migration step is unavailable.",
                        details={"feature_id": feature_id, "from_version": version,
                                 "target_version": target_version})
                values = self._apply_operations(values, migration["operations"])
                version = migration["to_version"]
            FeatureConfigurationManagerService._validate_configuration(schema_definition, values)
            updates.append((profile.scope, profile.scope_key, target_version, values))
        migrate = getattr(self._configurations, "migrate_profiles", None)
        if not callable(migrate):
            raise ApplicationError("FEATURE_MIGRATION_REPOSITORY_UNSUPPORTED",
                "Configuration repository does not support atomic profile migration.")
        migrate(feature_id, updates, actor_id)
        self._registry.audit(actor_id=actor_id, feature_id=feature_id, operation="configuration.migrated",
            previous_state=None, resulting_state=None, package_digest=package_digest, result="success")
        self._publish("feature.configuration.migrated", feature_id, actor_id,
                      {"profiles_migrated": len(updates), "target_version": target_version})
        return len(updates)

    def migrate_feature_data(self, *, feature_id: str, actor_id: str,
                             package_root: Path, from_version: int, to_version: int) -> Path:
        """Apply ordered SQL migrations to the feature's isolated SQLite data store."""
        self._authorization.require(actor_id, "feature.update", {"feature_id": feature_id})
        if from_version < 1 or to_version < 1 or to_version < from_version:
            raise ApplicationError("FEATURE_MIGRATION_VERSION_INVALID", "Migration versions are invalid.")
        if from_version == to_version:
            return self._data_path(feature_id)
        root, _manifest, package_digest = self._load_verified_manifest(feature_id, package_root)
        migration_dir = self._safe_child(root, "migrations/data")
        if migration_dir.exists() and not migration_dir.is_dir():
            raise ApplicationError("FEATURE_MIGRATION_PATH_INVALID", "Data migration path must be a directory.")
        migration_map = self._load_sql_migrations(migration_dir)
        chain: list[tuple[int, int, Path]] = []
        version = from_version
        while version < to_version:
            item = migration_map.get(version)
            if item is None or item[0] > to_version:
                raise ApplicationError("FEATURE_DATA_MIGRATION_MISSING",
                    "A required feature data migration step is unavailable.",
                    details={"feature_id": feature_id, "from_version": version,
                             "target_version": to_version})
            chain.append((version, item[0], item[1]))
            version = item[0]
        database_path = self._data_path(feature_id)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._backup_root.mkdir(parents=True, exist_ok=True)
        backup_path = self._backup_root / f"{feature_id}-data-v{from_version}-to-v{to_version}-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.sqlite3"
        try:
            with closing(sqlite3.connect(database_path)) as connection, connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("CREATE TABLE IF NOT EXISTS feature_migration_history (feature_id TEXT NOT NULL, from_version INTEGER NOT NULL, to_version INTEGER NOT NULL, migration_file TEXT NOT NULL, applied_at TEXT NOT NULL, applied_by TEXT NOT NULL, PRIMARY KEY(feature_id, from_version, to_version))")
                connection.execute("CREATE TABLE IF NOT EXISTS feature_data_schema (feature_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL CHECK(schema_version >= 1))")
                if database_path.exists() and database_path.stat().st_size:
                    with closing(sqlite3.connect(backup_path)) as backup:
                        connection.backup(backup)
                connection.execute("BEGIN IMMEDIATE")
                current_schema = connection.execute(
                    "SELECT schema_version FROM feature_data_schema WHERE feature_id=?", (feature_id,)
                ).fetchone()
                if current_schema is None:
                    connection.execute("INSERT INTO feature_data_schema(feature_id, schema_version) VALUES (?, ?)",
                                       (feature_id, from_version))
                elif int(current_schema[0]) != from_version:
                    raise ApplicationError("FEATURE_DATA_SCHEMA_VERSION_MISMATCH",
                        "Feature data store version does not match the requested migration source version.",
                        details={"stored_version": int(current_schema[0]), "requested_version": from_version})
                for source, target, script_path in chain:
                    existing = connection.execute(
                        "SELECT 1 FROM feature_migration_history WHERE feature_id=? AND from_version=? AND to_version=?",
                        (feature_id, source, target)).fetchone()
                    if existing:
                        raise ApplicationError("FEATURE_MIGRATION_ALREADY_APPLIED",
                            "Migration history conflicts with the requested source version.")
                    self._execute_sql_script(connection, script_path)
                    connection.execute(
                        "INSERT INTO feature_migration_history VALUES (?, ?, ?, ?, ?, ?)",
                        (feature_id, source, target, script_path.name, datetime.now(UTC).isoformat(), actor_id))
                connection.execute("UPDATE feature_data_schema SET schema_version=? WHERE feature_id=?",
                                   (to_version, feature_id))
                connection.commit()
        except ApplicationError:
            if backup_path.exists():
                backup_path.unlink()
            raise
        except (sqlite3.Error, OSError, UnicodeError) as exc:
            if backup_path.exists():
                backup_path.unlink()
            self._logger.exception("Feature data migration failed for %s", feature_id)
            raise ApplicationError("FEATURE_DATA_MIGRATION_FAILED",
                "Feature data migration failed; the transaction was rolled back.",
                details={"feature_id": feature_id}) from exc
        self._registry.audit(actor_id=actor_id, feature_id=feature_id, operation="data.migrated",
            previous_state=None, resulting_state=None, package_digest=package_digest, result="success")
        self._publish("feature.data.migrated", feature_id, actor_id,
                      {"from_version": from_version, "to_version": to_version,
                       "backup_available": backup_path.exists()})
        return backup_path if backup_path.exists() else database_path

    def _data_path(self, feature_id: str) -> Path:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", feature_id):
            raise ApplicationError("FEATURE_ID_INVALID", "Feature identifier is invalid.")
        path = (self._data_root / f"{feature_id}.sqlite3").resolve()
        candidate = self._data_root / f"{feature_id}.sqlite3"
        if candidate.is_symlink() or not path.is_relative_to(self._data_root):
            raise ApplicationError("FEATURE_DATA_PATH_INVALID", "Feature data path is unsafe or outside its data root.")
        return path

    def _load_verified_manifest(self, feature_id: str, package_root: Path) -> tuple[Path, FeatureManifest, str]:
        root = self._validated_package_root(package_root)
        package_digest = self._verifier.verify(feature_id, root)
        manifest = ManifestLoader().load(root)
        if manifest.feature_id != feature_id:
            raise ApplicationError("FEATURE_ID_MISMATCH", "Migration package feature_id does not match the requested feature.")
        return root, manifest, package_digest

    @staticmethod
    def _validated_package_root(package_root: Path) -> Path:
        source = Path(package_root)
        if source.is_symlink():
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Migration package root cannot be a symbolic link.")
        try:
            root = source.resolve(strict=True)
        except OSError as exc:
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Migration package root is unavailable.") from exc
        if not root.is_dir():
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Migration package root must be a directory.")
        return root

    @staticmethod
    def _safe_child(root: Path, relative: str) -> Path:
        candidate = root / relative
        if candidate.is_symlink():
            raise ApplicationError("FEATURE_MIGRATION_PATH_INVALID", "Migration directory cannot be a symbolic link.")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            raise ApplicationError("FEATURE_MIGRATION_PATH_INVALID", "Migration path escapes the package root.")
        return resolved

    @staticmethod
    def _load_configuration_migrations(directory: Path) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        if not directory.exists():
            return result
        for path in directory.iterdir():
            match = _MIGRATION_NAME.fullmatch(path.name)
            if not match or match.group("kind") != "json" or path.is_symlink() or not path.is_file():
                raise ApplicationError("FEATURE_MIGRATION_MANIFEST_INVALID", "Configuration migration directory contains an unexpected file.")
            source, target = int(match.group("source")), int(match.group("target"))
            if target != source + 1 or source in result:
                raise ApplicationError("FEATURE_MIGRATION_MANIFEST_INVALID", "Configuration migrations must be unique, sequential version steps.")
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ApplicationError("FEATURE_MIGRATION_MANIFEST_INVALID", "Configuration migration file is invalid JSON.") from exc
            if not isinstance(raw, dict) or raw.get("from_version") != source or raw.get("to_version") != target or not isinstance(raw.get("operations"), list):
                raise ApplicationError("FEATURE_MIGRATION_MANIFEST_INVALID", "Configuration migration metadata is invalid.")
            result[source] = raw
        return result

    @staticmethod
    def _load_sql_migrations(directory: Path) -> dict[int, tuple[int, Path]]:
        result: dict[int, tuple[int, Path]] = {}
        if not directory.exists():
            return result
        for path in directory.iterdir():
            match = _MIGRATION_NAME.fullmatch(path.name)
            if not match or match.group("kind") != "sql" or path.is_symlink() or not path.is_file():
                raise ApplicationError("FEATURE_MIGRATION_MANIFEST_INVALID", "Data migration directory contains an unexpected file.")
            source, target = int(match.group("source")), int(match.group("target"))
            if target != source + 1 or source in result:
                raise ApplicationError("FEATURE_MIGRATION_MANIFEST_INVALID", "Data migrations must be unique, sequential version steps.")
            result[source] = (target, path)
        return result

    @staticmethod
    def _apply_operations(values: dict[str, Any], operations: list[Any]) -> dict[str, Any]:
        result = dict(values)
        for operation in operations:
            if not isinstance(operation, dict):
                raise ApplicationError("FEATURE_MIGRATION_MANIFEST_INVALID", "Migration operation must be an object.")
            kind = operation.get("op")
            source = operation.get("field")
            if kind == "rename_field" and isinstance(source, str) and isinstance(operation.get("to"), str):
                target = operation["to"]
                if source in result:
                    if target in result:
                        raise ApplicationError("FEATURE_CONFIGURATION_MIGRATION_CONFLICT", "Cannot rename a field over an existing value.")
                    result[target] = result.pop(source)
            elif kind == "remove_field" and isinstance(source, str):
                result.pop(source, None)
            elif kind == "set_default" and isinstance(source, str) and "value" in operation:
                result.setdefault(source, operation["value"])
            elif kind == "map_value" and isinstance(source, str) and isinstance(operation.get("mapping"), dict):
                if source in result:
                    mapping = operation["mapping"]
                    old_value = result[source]
                    if isinstance(old_value, str) and old_value in mapping:
                        result[source] = mapping[old_value]
            else:
                raise ApplicationError("FEATURE_MIGRATION_MANIFEST_INVALID", "Configuration migration contains an unsupported operation.")
        try:
            json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ApplicationError("FEATURE_CONFIGURATION_MIGRATION_INVALID", "Migrated configuration is not JSON serializable.") from exc
        return result

    @staticmethod
    def _execute_sql_script(connection: sqlite3.Connection, path: Path) -> None:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ApplicationError("FEATURE_DATA_MIGRATION_INVALID", "Data migration script cannot be read.") from exc
        if _FORBIDDEN_SQL.search(source):
            raise ApplicationError("FEATURE_DATA_MIGRATION_INVALID", "Data migration contains a forbidden transaction or connection-control statement.")
        statement = ""
        for line in source.splitlines():
            statement += line + "\n"
            if sqlite3.complete_statement(statement):
                sql = statement.strip()
                statement = ""
                if sql:
                    connection.execute(sql)
        if statement.strip():
            raise ApplicationError("FEATURE_DATA_MIGRATION_INVALID", "Data migration contains an incomplete SQL statement.")

    def _publish(self, event_name: str, feature_id: str, actor_id: str, payload: Mapping[str, object]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(ApplicationEvent(event_name, actor_id=actor_id,
                payload={"feature_id": feature_id, **dict(payload)}))
