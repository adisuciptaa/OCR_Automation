"""Integration coverage for Feature Manager to trusted runtime activation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.event_bus import EventBus
from app.core.exceptions import ApplicationError
from app.core.service_registry import ServiceRegistry
from app.feature_manager.manager import FeatureManagerService
from app.feature_manager.models import PackageCandidate
from app.feature_manager.package_verifier import PackageVerifier
from app.feature_manager.runtime import FeatureRuntimeManager
from app.persistence.repositories.feature_registry_repository import SQLiteFeatureRegistryRepository


class _Authorization:
    def require(self, actor_id: str, permission: str, resource: object | None = None) -> None:
        if actor_id == "admin":
            return
        if actor_id == "operator" and permission.startswith("feature.view."):
            return
        raise ApplicationError("AUTH_PERMISSION_DENIED", "Not authorized.")

    def is_allowed(self, actor_id: str, permission: str, resource: object | None = None) -> bool:
        return actor_id in {"admin", "operator"}


def _write_feature_package(root: Path) -> None:
    root.mkdir(parents=True)
    manifest = {
        "manifest_schema_version": "1.0",
        "feature_id": "runtime_sample",
        "display_name": "Runtime Sample",
        "version": "1.0.0",
        "description": "Integration test feature",
        "publisher": "OCR Automation Tests",
        "entry_point": "plugin:RuntimeSampleFeature",
        "minimum_core_version": "0.1.0",
        "maximum_core_version": None,
        "api_contract_version": "2.3.0",
        "dependencies": {"features": [], "services": []},
        "permissions": [],
        "configuration_schema": "config_schema.json",
        "ui": {
            "navigation_label": "Runtime Sample",
            "icon": "file",
            "workspace": "ui:RuntimeSampleWorkspace",
        },
        "license_entitlement": None,
        "data_schema_version": 1,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "config_schema.json").write_text('{"type":"object"}', encoding="utf-8")
    (root / "ui.py").write_text(
        "class RuntimeSampleWorkspace:\n"
        "    def __init__(self, actor_id): self.actor_id = actor_id\n",
        encoding="utf-8",
    )
    (root / "plugin.py").write_text(
        "from .ui import RuntimeSampleWorkspace\n"
        "from app.feature_manager.models import FeatureDescriptor\n"
        "class RuntimeSampleFeature:\n"
        "    def initialize(self, context): self.context = context\n"
        "    def get_descriptor(self):\n"
        "        return FeatureDescriptor('runtime_sample', 'Runtime Sample', 'Integration test feature', '1.0.0', 'file', (), None)\n"
        "    def create_workspace(self, context): return RuntimeSampleWorkspace(context.actor_id)\n"
        "    def validate_configuration(self, config): return True\n"
        "    def execute(self, request): return request\n"
        "    def shutdown(self): self.closed = True\n",
        encoding="utf-8",
    )


def test_registered_and_enabled_feature_activates_through_runtime(tmp_path: Path) -> None:
    feature_root = tmp_path / "features"
    package_root = feature_root / "runtime_sample"
    _write_feature_package(package_root)
    digest = PackageVerifier.digest_directory(package_root)
    events = EventBus()
    services = ServiceRegistry()
    repository = SQLiteFeatureRegistryRepository(tmp_path / "registry.sqlite3")
    manager = FeatureManagerService(
        feature_root=feature_root,
        repository=repository,
        authorization=_Authorization(),
        service_provider=services.provider,
        event_bus=events,
        verifier=PackageVerifier({"runtime_sample": digest}),
    )
    manifest = manager.loader.load(package_root)
    manager.register(
        PackageCandidate(package_root, package_root / "manifest.json", manifest, digest),
        "admin",
    )
    manager.enable("runtime_sample", "admin")

    runtime = FeatureRuntimeManager(
        feature_manager=manager,
        services=services.provider,
        event_bus=events,
    )
    workspace = runtime.create_workspace("runtime_sample", "operator", object())
    assert workspace.actor_id == "operator"
    assert runtime.loaded_feature_ids() == ("runtime_sample",)

    manager.disable("runtime_sample", "admin")
    assert runtime.loaded_feature_ids() == ()
    runtime.shutdown_all()


def test_runtime_activation_fails_closed_after_package_tampering(tmp_path: Path) -> None:
    feature_root = tmp_path / "features"
    package_root = feature_root / "runtime_sample"
    _write_feature_package(package_root)
    digest = PackageVerifier.digest_directory(package_root)
    services = ServiceRegistry()
    events = EventBus()
    manager = FeatureManagerService(
        feature_root=feature_root,
        repository=SQLiteFeatureRegistryRepository(tmp_path / "registry.sqlite3"),
        authorization=_Authorization(),
        service_provider=services.provider,
        event_bus=events,
        verifier=PackageVerifier({"runtime_sample": digest}),
    )
    manifest = manager.loader.load(package_root)
    manager.register(
        PackageCandidate(package_root, package_root / "manifest.json", manifest, digest),
        "admin",
    )
    manager.enable("runtime_sample", "admin")
    (package_root / "plugin.py").write_text("# changed after install\n", encoding="utf-8")

    runtime = FeatureRuntimeManager(
        feature_manager=manager,
        services=services.provider,
        event_bus=events,
    )
    with pytest.raises(ApplicationError) as error:
        runtime.activate("runtime_sample", "operator")
    assert error.value.code == "FEATURE_SIGNATURE_INVALID"
    assert runtime.loaded_feature_ids() == ()
    runtime.shutdown_all()
