from datetime import UTC, datetime
import json
import sqlite3

import pytest

from app.core.exceptions import ApplicationError
from app.feature_manager.migration_engine import FeatureDataMigrationEngine
from app.feature_manager.models import ConfigurationScope, FeatureConfiguration
from app.persistence.repositories.feature_configuration_repository import SQLiteFeatureConfigurationRepository


class AuditRegistry:
    def __init__(self):
        self.entries = []

    def audit(self, **entry):
        self.entries.append(entry)


class TrustedPackageVerifier:
    def verify(self, feature_id, package_path):
        assert package_path.is_dir()
        return "sha256:test-digest"


class AllowAllAuthorization:
    def require(self, actor_id, permission, resource=None):
        assert actor_id == "admin"
        assert permission in {"feature.configure.invoice_reader", "feature.update"}


def _write_package(package, schema=None):
    package.mkdir(parents=True, exist_ok=True)
    definition = schema or {"type": "object", "properties": {}}
    (package / "config_schema.json").write_text(json.dumps(definition), encoding="utf-8")
    manifest = {
        "manifest_schema_version": "1.0", "feature_id": "invoice_reader",
        "display_name": "Invoice Reader", "version": "2.0.0",
        "description": "Test feature", "publisher": "Test Publisher",
        "entry_point": "plugin:Feature", "minimum_core_version": "0.1.0",
        "maximum_core_version": None, "api_contract_version": "2.7.0",
        "dependencies": {"features": [], "services": []}, "permissions": [],
        "configuration_schema": "config_schema.json",
        "ui": {"navigation_label": "Invoice Reader", "icon": "file", "workspace": "ui:Workspace"},
        "license_entitlement": None, "data_schema_version": 2
    }
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _engine(tmp_path, repository):
    return FeatureDataMigrationEngine(
        configurations=repository,
        authorization=AllowAllAuthorization(),
        registry=AuditRegistry(),
        data_root=tmp_path / "feature-data",
        backup_root=tmp_path / "backups",
        verifier=TrustedPackageVerifier(),
    )


def test_configuration_profiles_migrate_atomically(tmp_path):
    repository = SQLiteFeatureConfigurationRepository(tmp_path / "app.sqlite3")
    now = datetime.now(UTC)
    repository.save(FeatureConfiguration("invoice_reader", ConfigurationScope.USER, "u1", 1,
        {"old_name": "legacy", "mode": "basic"}, now, now, "admin"))
    package = tmp_path / "package"
    _write_package(package, {"type": "object", "x-config-version": 2, "properties": {
        "new_name": {"type": "string"}, "mode": {"type": "string", "enum": ["standard"]},
        "enabled": {"type": "boolean"}}, "required": ["new_name", "mode", "enabled"], "additionalProperties": False})
    migration_dir = package / "migrations" / "configuration"
    migration_dir.mkdir(parents=True)
    (migration_dir / "0001_to_0002.json").write_text(
        '{"from_version":1,"to_version":2,"operations":['
        '{"op":"rename_field","field":"old_name","to":"new_name"},'
        '{"op":"map_value","field":"mode","mapping":{"basic":"standard"}},'
        '{"op":"set_default","field":"enabled","value":true}]}', encoding="utf-8")

    count = _engine(tmp_path, repository).migrate_configuration_profiles(
        feature_id="invoice_reader", actor_id="admin", package_root=package, target_version=2)

    migrated = repository.get("invoice_reader", ConfigurationScope.USER, "u1")
    assert count == 1
    assert migrated.schema_version == 2
    assert dict(migrated.values) == {"new_name": "legacy", "mode": "standard", "enabled": True}
    assert migrated.updated_by == "admin"


def test_configuration_migration_rejects_missing_step_without_mutation(tmp_path):
    repository = SQLiteFeatureConfigurationRepository(tmp_path / "app.sqlite3")
    now = datetime.now(UTC)
    original = FeatureConfiguration("invoice_reader", ConfigurationScope.USER, "u1", 1,
        {"name": "legacy"}, now, now, "admin")
    repository.save(original)
    package = tmp_path / "package"
    _write_package(package, {"type": "object", "x-config-version": 2, "properties": {"name": {"type": "string"}}})
    with pytest.raises(ApplicationError) as error:
        _engine(tmp_path, repository).migrate_configuration_profiles(
            feature_id="invoice_reader", actor_id="admin", package_root=package, target_version=2)
    assert error.value.code == "FEATURE_CONFIGURATION_MIGRATION_MISSING"
    assert repository.get("invoice_reader", ConfigurationScope.USER, "u1") == original


def test_feature_data_sql_migration_and_backup(tmp_path):
    repository = SQLiteFeatureConfigurationRepository(tmp_path / "app.sqlite3")
    package = tmp_path / "package"
    _write_package(package)
    migration_dir = package / "migrations" / "data"
    migration_dir.mkdir(parents=True)
    (migration_dir / "0001_to_0002.sql").write_text(
        "CREATE TABLE invoices (invoice_no TEXT NOT NULL);\n"
        "INSERT INTO invoices(invoice_no) VALUES ('000123');\n", encoding="utf-8")
    engine = _engine(tmp_path, repository)

    backup = engine.migrate_feature_data(feature_id="invoice_reader", actor_id="admin",
        package_root=package, from_version=1, to_version=2)

    database = tmp_path / "feature-data" / "invoice_reader.sqlite3"
    assert database.exists()
    assert backup.exists()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT invoice_no FROM invoices").fetchone()[0] == "000123"
        assert connection.execute("SELECT to_version FROM feature_migration_history").fetchone()[0] == 2
        assert connection.execute("SELECT schema_version FROM feature_data_schema").fetchone()[0] == 2


def test_feature_data_sql_failure_rolls_back_schema_changes(tmp_path):
    repository = SQLiteFeatureConfigurationRepository(tmp_path / "app.sqlite3")
    package = tmp_path / "package"
    _write_package(package)
    migration_dir = package / "migrations" / "data"
    migration_dir.mkdir(parents=True)
    (migration_dir / "0001_to_0002.sql").write_text(
        "CREATE TABLE should_rollback (id INTEGER);\n"
        "INSERT INTO missing_table VALUES (1);\n", encoding="utf-8")
    engine = _engine(tmp_path, repository)

    with pytest.raises(ApplicationError) as error:
        engine.migrate_feature_data(feature_id="invoice_reader", actor_id="admin",
            package_root=package, from_version=1, to_version=2)
    assert error.value.code == "FEATURE_DATA_MIGRATION_FAILED"
    database = tmp_path / "feature-data" / "invoice_reader.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='should_rollback'").fetchone() is None


def test_feature_data_migration_rejects_transaction_control_sql(tmp_path):
    repository = SQLiteFeatureConfigurationRepository(tmp_path / "app.sqlite3")
    package = tmp_path / "package"
    _write_package(package)
    migration_dir = package / "migrations" / "data"
    migration_dir.mkdir(parents=True)
    (migration_dir / "0001_to_0002.sql").write_text("COMMIT;\n", encoding="utf-8")
    with pytest.raises(ApplicationError) as error:
        _engine(tmp_path, repository).migrate_feature_data(feature_id="invoice_reader", actor_id="admin",
            package_root=package, from_version=1, to_version=2)
    assert error.value.code == "FEATURE_DATA_MIGRATION_INVALID"


def test_feature_data_migration_checks_persisted_schema_version(tmp_path):
    repository = SQLiteFeatureConfigurationRepository(tmp_path / "app.sqlite3")
    package = tmp_path / "package"
    _write_package(package)
    migration_dir = package / "migrations" / "data"
    migration_dir.mkdir(parents=True)
    (migration_dir / "0001_to_0002.sql").write_text("CREATE TABLE records (id INTEGER);\n", encoding="utf-8")
    engine = _engine(tmp_path, repository)
    engine.migrate_feature_data(feature_id="invoice_reader", actor_id="admin",
        package_root=package, from_version=1, to_version=2)
    with pytest.raises(ApplicationError) as error:
        engine.migrate_feature_data(feature_id="invoice_reader", actor_id="admin",
            package_root=package, from_version=1, to_version=2)
    assert error.value.code == "FEATURE_DATA_SCHEMA_VERSION_MISMATCH"
