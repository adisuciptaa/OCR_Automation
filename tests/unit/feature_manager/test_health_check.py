from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.core.exceptions import ApplicationError
from app.feature_manager.health_check import FeatureHealthCheckManager
from app.feature_manager.manifest_loader import ManifestLoader
from app.feature_manager.models import FeatureRecord, FeatureState
from app.feature_manager.package_verifier import PackageVerifier
from app.feature_manager.rollback import FeatureRollbackCoordinator


class AllowAuthorization:
    def require(self, actor_id, permission, resource=None):
        assert actor_id in {"admin", "system.recovery"}
        assert permission in {"feature.update"}


class Registry:
    def __init__(self, record):
        self.record = record
        self.audit_entries = []

    def get(self, feature_id):
        return self.record if self.record and self.record.feature_id == feature_id else None

    def save(self, record):
        self.record = record

    def audit(self, **entry):
        self.audit_entries.append(entry)


class Configurations:
    def list_for_feature(self, feature_id):
        return ()


class Services:
    def get(self, service_id, version=None):
        raise AssertionError("No service dependencies are expected in this test.")


def write_package(path, version="1.0.0"):
    path.mkdir(parents=True, exist_ok=True)
    (path / "config_schema.json").write_text(json.dumps({
        "type": "object", "x-config-version": 1, "properties": {}, "additionalProperties": False
    }), encoding="utf-8")
    manifest = {
        "manifest_schema_version": "1.0", "feature_id": "invoice_reader",
        "display_name": "Invoice Reader", "version": version, "description": "Test feature",
        "publisher": "Test Publisher", "entry_point": "plugin:Feature",
        "minimum_core_version": "0.1.0", "maximum_core_version": None,
        "api_contract_version": "2.7.0",
        "dependencies": {"features": [], "services": []}, "permissions": [],
        "configuration_schema": "config_schema.json",
        "ui": {"navigation_label": "Invoice Reader", "icon": "file", "workspace": "ui:Workspace"},
        "license_entitlement": None, "data_schema_version": 1,
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (path / "plugin.py").write_text("# trusted test package\n", encoding="utf-8")


def make_record(package, verifier):
    manifest = ManifestLoader().load(package)
    digest = verifier.verify("invoice_reader", package)
    now = datetime.now(UTC)
    return FeatureRecord(manifest, str(package), digest, "verified", FeatureState.ENABLED, now, now)


def test_health_check_reports_healthy_feature(tmp_path):
    package = tmp_path / "package"
    write_package(package)
    digest = PackageVerifier.digest_directory(package)
    verifier = PackageVerifier({"invoice_reader": digest})
    record = make_record(package, verifier)
    manager = FeatureHealthCheckManager(
        registry=Registry(record), configurations=Configurations(),
        authorization=AllowAuthorization(), services=Services(), verifier=verifier,
        data_root=tmp_path / "feature-data",
    )
    report = manager.check_feature("invoice_reader", "admin")
    assert report.status.value == "healthy"
    assert {item.check_id for item in report.checks} == {
        "package_integrity", "configuration", "feature_data"
    }


def test_health_check_detects_tampered_package(tmp_path):
    package = tmp_path / "package"
    write_package(package)
    verifier = PackageVerifier({"invoice_reader": PackageVerifier.digest_directory(package)})
    record = make_record(package, verifier)
    (package / "plugin.py").write_text("# tampered\n", encoding="utf-8")
    manager = FeatureHealthCheckManager(
        registry=Registry(record), configurations=Configurations(),
        authorization=AllowAuthorization(), services=Services(), verifier=verifier,
        data_root=tmp_path / "feature-data",
    )
    report = manager.check_feature("invoice_reader", "admin")
    assert report.status.value == "unhealthy"
    assert report.checks[0].error_code == "FEATURE_SIGNATURE_INVALID"


def test_rollback_restores_verified_package_and_registry(tmp_path):
    package = tmp_path / "features" / "invoice_reader"
    write_package(package, "1.0.0")
    verifier = PackageVerifier({"invoice_reader": PackageVerifier.digest_directory(package)})
    old_record = make_record(package, verifier)
    registry = Registry(old_record)
    coordinator = FeatureRollbackCoordinator(
        registry=registry, authorization=AllowAuthorization(),
        backup_root=tmp_path / "rollback", verifier=verifier,
    )
    checkpoint_id = coordinator.create_checkpoint("invoice_reader", "admin")

    # Simulate a package update and registry record replacement.
    write_package(package, "2.0.0")
    updated_digest = PackageVerifier.digest_directory(package)
    updated_verifier = PackageVerifier({"invoice_reader": [updated_digest, old_record.package_digest]})
    # Rebind coordinator to an allowlist that trusts both current and checkpoint packages.
    coordinator._verifier = updated_verifier
    updated_record = make_record(package, updated_verifier)
    registry.save(updated_record)

    restored = coordinator.rollback(checkpoint_id, "admin")
    assert restored.manifest.version == "1.0.0"
    assert ManifestLoader().load(package).version == "1.0.0"
    assert registry.record.package_digest == old_record.package_digest


def test_rollback_rejects_unknown_checkpoint(tmp_path):
    verifier = PackageVerifier()
    coordinator = FeatureRollbackCoordinator(
        registry=Registry(None), authorization=AllowAuthorization(),
        backup_root=tmp_path / "rollback", verifier=verifier,
    )
    with pytest.raises(ApplicationError) as error:
        coordinator.rollback("not-a-real-checkpoint", "admin")
    assert error.value.code in {"FEATURE_ROLLBACK_CHECKPOINT_MISSING", "FEATURE_ROLLBACK_CHECKPOINT_INVALID"}


def test_committed_checkpoint_is_not_recovered_automatically(tmp_path):
    package = tmp_path / "features" / "invoice_reader"
    write_package(package, "1.0.0")
    old_digest = PackageVerifier.digest_directory(package)
    verifier = PackageVerifier({"invoice_reader": old_digest})
    record = make_record(package, verifier)
    registry = Registry(record)
    coordinator = FeatureRollbackCoordinator(
        registry=registry, authorization=AllowAuthorization(),
        backup_root=tmp_path / "rollback", verifier=verifier,
    )
    checkpoint_id = coordinator.create_checkpoint("invoice_reader", "admin")
    coordinator.complete_checkpoint(checkpoint_id, "admin")
    assert coordinator.recover_pending() == ()
    journal = json.loads((tmp_path / "rollback" / checkpoint_id / "journal.json").read_text())
    assert journal["status"] == "committed"


def test_prepared_checkpoint_is_recovered_after_interrupted_update(tmp_path):
    package = tmp_path / "features" / "invoice_reader"
    write_package(package, "1.0.0")
    old_digest = PackageVerifier.digest_directory(package)
    verifier = PackageVerifier({"invoice_reader": old_digest})
    old_record = make_record(package, verifier)
    registry = Registry(old_record)
    coordinator = FeatureRollbackCoordinator(
        registry=registry, authorization=AllowAuthorization(),
        backup_root=tmp_path / "rollback", verifier=verifier,
    )
    checkpoint_id = coordinator.create_checkpoint("invoice_reader", "admin")
    write_package(package, "2.0.0")
    updated_digest = PackageVerifier.digest_directory(package)
    coordinator._verifier = PackageVerifier({"invoice_reader": [old_digest, updated_digest]})
    registry.save(make_record(package, coordinator._verifier))
    assert coordinator.recover_pending() == (checkpoint_id,)
    assert ManifestLoader().load(package).version == "1.0.0"
    assert registry.record.package_digest == old_digest


def test_health_check_detects_feature_data_schema_version_mismatch(tmp_path):
    import sqlite3

    package = tmp_path / "package"
    write_package(package)
    verifier = PackageVerifier({"invoice_reader": PackageVerifier.digest_directory(package)})
    record = make_record(package, verifier)
    data_root = tmp_path / "feature-data"
    data_root.mkdir()
    with sqlite3.connect(data_root / "invoice_reader.sqlite3") as connection:
        connection.execute("CREATE TABLE feature_data_schema (feature_id TEXT PRIMARY KEY, schema_version INTEGER)")
        connection.execute("INSERT INTO feature_data_schema VALUES ('invoice_reader', 99)")
    manager = FeatureHealthCheckManager(
        registry=Registry(record), configurations=Configurations(),
        authorization=AllowAuthorization(), services=Services(), verifier=verifier,
        data_root=data_root,
    )
    report = manager.check_feature("invoice_reader", "admin")
    data_check = next(item for item in report.checks if item.check_id == "feature_data")
    assert data_check.status.value == "unhealthy"
    assert data_check.error_code == "FEATURE_DATA_INTEGRITY_FAILED"
