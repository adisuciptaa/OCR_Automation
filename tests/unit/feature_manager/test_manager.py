from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.event_bus import EventBus
from app.core.exceptions import ApplicationError
from app.core.service_registry import ServiceRegistry
from app.feature_manager.manager import FeatureManagerService
from app.feature_manager.models import FeatureState, PackageCandidate
from app.feature_manager.package_verifier import PackageVerifier
from app.persistence.repositories.feature_registry_repository import SQLiteFeatureRegistryRepository


class AllowAuthorization:
    def require(self, actor_id, permission, resource=None):
        if actor_id != "admin":
            raise ApplicationError("FEATURE_PERMISSION_DENIED", "Denied")

    def is_allowed(self, actor_id, permission, resource=None):
        return actor_id == "admin"


def _package(root):
    root.mkdir(parents=True)
    manifest = {
        "manifest_schema_version": "1.0", "feature_id": "sample_reader",
        "display_name": "Sample Reader", "version": "1.0.0", "description": "Sample",
        "publisher": "OCR Automation", "entry_point": "plugin:SampleFeature",
        "minimum_core_version": "0.1.0", "maximum_core_version": None,
        "api_contract_version": "2.1.0", "dependencies": {"features": [], "services": []},
        "permissions": ["filesystem.read_input"], "configuration_schema": "config_schema.json",
        "ui": {"navigation_label": "Sample", "icon": "file", "workspace": "ui:SampleWorkspace"},
        "license_entitlement": None, "data_schema_version": 1,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "config_schema.json").write_text('{"type":"object"}', encoding="utf-8")
    (root / "plugin.py").write_text("class SampleFeature: pass\n", encoding="utf-8")
    return manifest


def _manager(tmp_path, feature_root, digest, license_check=None):
    repository = SQLiteFeatureRegistryRepository(tmp_path / "registry.sqlite3")
    services = ServiceRegistry()
    return FeatureManagerService(feature_root=feature_root, repository=repository,
        authorization=AllowAuthorization(), service_provider=services.provider,
        event_bus=EventBus(), verifier=PackageVerifier({"sample_reader": digest}),
        license_check=license_check), repository


def test_register_enable_and_authorized_catalog(tmp_path):
    feature_root = tmp_path / "features"
    package = feature_root / "sample_reader"
    _package(package)
    digest = PackageVerifier.digest_directory(package)
    manager, repository = _manager(tmp_path, feature_root, digest)
    manifest = manager.loader.load(package)
    candidate = PackageCandidate(package, package / "manifest.json", manifest, digest)

    registered = manager.register(candidate, "admin")
    assert registered.state is FeatureState.REGISTERED
    enabled = manager.enable("sample_reader", "admin")
    assert enabled.state is FeatureState.ENABLED
    assert [item.feature_id for item in manager.list_available("admin")] == ["sample_reader"]
    assert manager.list_available("guest") == ()
    assert repository.get("sample_reader").state is FeatureState.ENABLED



def test_missing_entitlement_bypasses_custom_license_checker_across_lifecycle(tmp_path):
    feature_root = tmp_path / "features"
    package = feature_root / "sample_reader"
    _package(package)
    digest = PackageVerifier.digest_directory(package)
    checker_calls = []

    def reject_every_entitlement(entitlement):
        checker_calls.append(entitlement)
        return False

    manager, _ = _manager(tmp_path, feature_root, digest, license_check=reject_every_entitlement)
    candidate = PackageCandidate(package, package / "manifest.json", manager.loader.load(package), digest)
    manager.register(candidate, "admin")

    enabled = manager.enable("sample_reader", "admin")
    assert enabled.state is FeatureState.ENABLED
    assert manager.get_enabled_feature("sample_reader", "admin").feature_id == "sample_reader"
    assert [item.feature_id for item in manager.list_available("admin")] == ["sample_reader"]
    assert checker_calls == []


def test_declared_entitlement_is_checked_by_custom_license_provider(tmp_path):
    feature_root = tmp_path / "features"
    package = feature_root / "sample_reader"
    manifest = _package(package)
    manifest["license_entitlement"] = "feature.sample_reader"
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    digest = PackageVerifier.digest_directory(package)
    manager, _ = _manager(
        tmp_path, feature_root, digest,
        license_check=lambda entitlement: entitlement == "feature.sample_reader",
    )
    candidate = PackageCandidate(package, package / "manifest.json", manager.loader.load(package), digest)
    manager.register(candidate, "admin")

    assert manager.enable("sample_reader", "admin").state is FeatureState.ENABLED


def test_unavailable_declared_entitlement_blocks_enable(tmp_path):
    feature_root = tmp_path / "features"
    package = feature_root / "sample_reader"
    manifest = _package(package)
    manifest["license_entitlement"] = "feature.sample_reader"
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    digest = PackageVerifier.digest_directory(package)
    manager, _ = _manager(tmp_path, feature_root, digest, license_check=lambda _entitlement: False)
    candidate = PackageCandidate(package, package / "manifest.json", manager.loader.load(package), digest)
    manager.register(candidate, "admin")

    with pytest.raises(ApplicationError) as error:
        manager.enable("sample_reader", "admin")
    assert error.value.code == "FEATURE_LICENSE_INVALID"

def test_register_rejects_untrusted_digest(tmp_path):
    feature_root = tmp_path / "features"
    package = feature_root / "sample_reader"
    _package(package)
    digest = PackageVerifier.digest_directory(package)
    manager, _ = _manager(tmp_path, feature_root, "sha256:" + "0" * 64)
    candidate = PackageCandidate(package, package / "manifest.json", manager.loader.load(package), digest)
    with pytest.raises(ApplicationError) as error:
        manager.register(candidate, "admin")
    assert error.value.code == "FEATURE_SIGNATURE_INVALID"


def test_disable_and_uninstall_retain_package_backup(tmp_path):
    feature_root = tmp_path / "features"
    package = feature_root / "sample_reader"
    _package(package)
    digest = PackageVerifier.digest_directory(package)
    manager, _ = _manager(tmp_path, feature_root, digest)
    candidate = PackageCandidate(package, package / "manifest.json", manager.loader.load(package), digest)
    manager.register(candidate, "admin")
    manager.enable("sample_reader", "admin")
    disabled = manager.disable("sample_reader", "admin")
    assert disabled.state is FeatureState.DISABLED
    uninstalled = manager.uninstall("sample_reader", "admin")
    assert uninstalled.state is FeatureState.UNINSTALLED
    assert not package.exists()
    assert list((tmp_path / "backups" / "features").glob("sample_reader-*-uninstalled"))


def test_update_retains_previous_package_and_preserves_enabled_state(tmp_path):
    feature_root = tmp_path / "features"
    package = feature_root / "sample_reader"
    manifest = _package(package)
    old_digest = PackageVerifier.digest_directory(package)
    updated_root = tmp_path / "updated"
    _package(updated_root)
    manifest["version"] = "1.1.0"
    (updated_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    new_digest = PackageVerifier.digest_directory(updated_root)

    repository = SQLiteFeatureRegistryRepository(tmp_path / "registry.sqlite3")
    services = ServiceRegistry()
    manager = FeatureManagerService(feature_root=feature_root, repository=repository,
        authorization=AllowAuthorization(), service_provider=services.provider, event_bus=EventBus(),
        verifier=PackageVerifier({"sample_reader": [old_digest, new_digest]}))
    original = PackageCandidate(package, package / "manifest.json", manager.loader.load(package), old_digest)
    manager.register(original, "admin")
    manager.enable("sample_reader", "admin")

    updated = manager.update("sample_reader", str(updated_root), "admin")
    assert updated.manifest.version == "1.1.0"
    assert updated.state is FeatureState.ENABLED
    assert PackageVerifier.digest_directory(package) == new_digest
    backups = list((tmp_path / "backups" / "features").glob("sample_reader-1.0.0-*"))
    assert len(backups) == 1
    assert PackageVerifier.digest_directory(backups[0]) == old_digest


def test_install_archive_runs_verification_and_registration(tmp_path):
    import zipfile

    feature_root = tmp_path / "features"
    source = tmp_path / "source"
    _package(source)
    digest = PackageVerifier.digest_directory(source)
    manager, repository = _manager(tmp_path, feature_root, digest)
    archive = tmp_path / "sample_reader.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in source.iterdir():
            bundle.write(path, path.name)
    installed = manager.install_archive(str(archive), "admin")
    assert installed.state is FeatureState.REGISTERED
    assert Path(installed.package_path).is_relative_to(feature_root)
    assert repository.get("sample_reader") is not None


def test_untrusted_archive_is_copied_to_quarantine(tmp_path):
    import zipfile

    feature_root = tmp_path / "features"
    source = tmp_path / "source"
    _package(source)
    digest = PackageVerifier.digest_directory(source)
    manager, _ = _manager(tmp_path, feature_root, "sha256:" + "0" * 64)
    archive = tmp_path / "untrusted.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in source.iterdir():
            bundle.write(path, path.name)
    with pytest.raises(ApplicationError):
        manager.install_archive(str(archive), "admin")
    quarantined = list((tmp_path / "quarantine" / "packages").glob("*.quarantined"))
    assert len(quarantined) == 1


def test_validation_rejects_feature_dependency_cycle(tmp_path):
    feature_root = tmp_path / "features"
    package = feature_root / "sample_reader"
    manifest = _package(package)
    manifest["dependencies"]["features"] = [{"id": "sample_reader", "version": "1.x"}]
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    digest = PackageVerifier.digest_directory(package)
    manager, _ = _manager(tmp_path, feature_root, digest)
    candidate = PackageCandidate(package, package / "manifest.json", manager.loader.load(package), digest)
    result = manager.validate(candidate)
    assert not result.valid
    assert "FEATURE_DEPENDENCY_CYCLE" in result.errors


def test_runtime_record_requires_enabled_state_and_feature_view_permission(tmp_path):
    feature_root = tmp_path / "features"
    package = feature_root / "sample_reader"
    _package(package)
    digest = PackageVerifier.digest_directory(package)
    manager, _ = _manager(tmp_path, feature_root, digest)
    candidate = PackageCandidate(package, package / "manifest.json", manager.loader.load(package), digest)
    manager.register(candidate, "admin")

    with pytest.raises(ApplicationError) as disabled_error:
        manager.get_enabled_feature("sample_reader", "admin")
    assert disabled_error.value.code == "FEATURE_NOT_AVAILABLE"

    manager.enable("sample_reader", "admin")
    assert manager.get_enabled_feature("sample_reader", "admin").feature_id == "sample_reader"

    with pytest.raises(ApplicationError) as denied_error:
        manager.get_enabled_feature("sample_reader", "guest")
    assert denied_error.value.code == "FEATURE_PERMISSION_DENIED"


def test_runtime_record_rechecks_package_integrity(tmp_path):
    feature_root = tmp_path / "features"
    package = feature_root / "sample_reader"
    _package(package)
    digest = PackageVerifier.digest_directory(package)
    manager, _ = _manager(tmp_path, feature_root, digest)
    candidate = PackageCandidate(package, package / "manifest.json", manager.loader.load(package), digest)
    manager.register(candidate, "admin")
    manager.enable("sample_reader", "admin")
    (package / "plugin.py").write_text("# modified after verification\n", encoding="utf-8")

    with pytest.raises(ApplicationError) as error:
        manager.get_enabled_feature("sample_reader", "admin")
    assert error.value.code == "FEATURE_SIGNATURE_INVALID"


def test_update_requires_healthy_post_update_report_and_commits_checkpoint(tmp_path):
    from app.feature_manager.health_check import FeatureHealthCheckManager
    from app.feature_manager.rollback import FeatureRollbackCoordinator
    from app.persistence.repositories.feature_configuration_repository import SQLiteFeatureConfigurationRepository

    feature_root = tmp_path / "features"
    package = feature_root / "sample_reader"
    manifest = _package(package)
    old_digest = PackageVerifier.digest_directory(package)
    updated_root = tmp_path / "updated"
    _package(updated_root)
    manifest["version"] = "1.1.0"
    (updated_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    new_digest = PackageVerifier.digest_directory(updated_root)

    repository = SQLiteFeatureRegistryRepository(tmp_path / "registry.sqlite3")
    configurations = SQLiteFeatureConfigurationRepository(tmp_path / "registry.sqlite3")
    services = ServiceRegistry()
    verifier = PackageVerifier({"sample_reader": [old_digest, new_digest]})
    health = FeatureHealthCheckManager(
        registry=repository, configurations=configurations,
        authorization=AllowAuthorization(), services=services.provider,
        verifier=verifier, data_root=tmp_path / "feature-data",
    )
    rollback = FeatureRollbackCoordinator(
        registry=repository, authorization=AllowAuthorization(),
        backup_root=tmp_path / "rollback", verifier=verifier,
    )
    manager = FeatureManagerService(
        feature_root=feature_root, repository=repository,
        authorization=AllowAuthorization(), service_provider=services.provider,
        event_bus=EventBus(), verifier=verifier,
        health_check_manager=health, rollback_coordinator=rollback,
    )
    original = PackageCandidate(package, package / "manifest.json", manager.loader.load(package), old_digest)
    manager.register(original, "admin")
    manager.enable("sample_reader", "admin")
    updated = manager.update("sample_reader", str(updated_root), "admin")
    assert updated.manifest.version == "1.1.0"
    journals = list((tmp_path / "rollback").glob("*/journal.json"))
    assert len(journals) == 1
    assert json.loads(journals[0].read_text())["status"] == "committed"


def test_update_automatically_rolls_back_when_health_check_fails(tmp_path):
    from types import SimpleNamespace
    from app.feature_manager.rollback import FeatureRollbackCoordinator

    feature_root = tmp_path / "features"
    package = feature_root / "sample_reader"
    manifest = _package(package)
    old_digest = PackageVerifier.digest_directory(package)
    updated_root = tmp_path / "updated"
    _package(updated_root)
    manifest["version"] = "1.1.0"
    (updated_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    new_digest = PackageVerifier.digest_directory(updated_root)

    repository = SQLiteFeatureRegistryRepository(tmp_path / "registry.sqlite3")
    services = ServiceRegistry()
    verifier = PackageVerifier({"sample_reader": [old_digest, new_digest]})
    rollback = FeatureRollbackCoordinator(
        registry=repository, authorization=AllowAuthorization(),
        backup_root=tmp_path / "rollback", verifier=verifier,
    )

    class Unhealthy:
        def check_feature(self, feature_id, actor_id):
            return SimpleNamespace(status=SimpleNamespace(value="unhealthy"))

    manager = FeatureManagerService(
        feature_root=feature_root, repository=repository,
        authorization=AllowAuthorization(), service_provider=services.provider,
        event_bus=EventBus(), verifier=verifier,
        health_check_manager=Unhealthy(), rollback_coordinator=rollback,
    )
    original = PackageCandidate(package, package / "manifest.json", manager.loader.load(package), old_digest)
    manager.register(original, "admin")
    manager.enable("sample_reader", "admin")
    with pytest.raises(ApplicationError) as error:
        manager.update("sample_reader", str(updated_root), "admin")
    assert error.value.code == "FEATURE_HEALTH_CHECK_FAILED"
    assert PackageVerifier.digest_directory(package) == old_digest
    assert repository.get("sample_reader").manifest.version == "1.0.0"
