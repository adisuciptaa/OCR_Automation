"""Contract and lifecycle tests for trusted feature runtime activation."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.event_bus import ApplicationEvent, EventBus
from app.core.exceptions import ApplicationError
from app.core.service_registry import ServiceRegistry
from app.feature_manager.models import (
    FeatureDependencies,
    FeatureDescriptor,
    FeatureManifest,
    FeatureRecord,
    FeatureState,
    ServiceDependency,
)
from app.feature_manager.runtime import FeatureRuntimeManager


class _FeatureManager:
    def __init__(self, record: FeatureRecord) -> None:
        self.record = record
        self.actors: list[tuple[str, str]] = []

    def get_enabled_feature(self, feature_id: str, actor_id: str) -> FeatureRecord:
        self.actors.append((feature_id, actor_id))
        if feature_id != self.record.feature_id:
            raise ApplicationError("FEATURE_NOT_FOUND", "Feature not found.")
        return self.record


def _record(
    root: Path,
    *,
    digest: str = "sha256:" + "a" * 64,
    dependencies: FeatureDependencies | None = None,
) -> FeatureRecord:
    (root / "plugin.py").write_text(
        "from .helper import LABEL\n"
        "from .ui import SampleWorkspace\n"
        "from app.feature_manager.models import FeatureDescriptor\n"
        "class SampleFeature:\n"
        "    def __init__(self): self.context = None; self.closed = False\n"
        "    def initialize(self, context): self.context = context\n"
        "    def get_descriptor(self):\n"
        "        return FeatureDescriptor('sample_feature', 'Sample', 'Test feature', '1.0.0', 'file', (), None)\n"
        "    def create_workspace(self, context): return SampleWorkspace(LABEL, context.feature_id, context.actor_id, context.parent)\n"
        "    def validate_configuration(self, config): return True\n"
        "    def execute(self, request): return request\n"
        "    def shutdown(self): self.closed = True\n",
        encoding="utf-8",
    )
    (root / "helper.py").write_text("LABEL = 'workspace'\n", encoding="utf-8")
    (root / "ui.py").write_text(
        "class SampleWorkspace:\n"
        "    def __init__(self, label, feature_id, actor_id, parent):\n"
        "        self.label = label; self.feature_id = feature_id; self.actor_id = actor_id; self.parent = parent\n",
        encoding="utf-8",
    )
    manifest = FeatureManifest(
        manifest_schema_version="1.0", feature_id="sample_feature", display_name="Sample",
        version="1.0.0", description="Test feature", publisher="Tests",
        entry_point="plugin:SampleFeature", minimum_core_version="0.1.0",
        api_contract_version="2.3.0", dependencies=dependencies or FeatureDependencies(), permissions=(),
        configuration_schema="config_schema.json", navigation_label="Sample", icon="file",
        workspace="ui:SampleWorkspace", data_schema_version=1,
    )
    return FeatureRecord(
        manifest, str(root), digest, "verified", FeatureState.ENABLED,
        datetime.now(UTC), datetime.now(UTC),
    )


def test_runtime_loads_once_and_creates_workspace_with_public_context(tmp_path: Path) -> None:
    record = _record(tmp_path)
    feature_manager = _FeatureManager(record)
    events = EventBus()
    runtime = FeatureRuntimeManager(
        feature_manager=feature_manager,
        services=ServiceRegistry().provider,
        event_bus=events,
    )
    parent = object()

    first = runtime.activate("sample_feature", "user-1")
    second = runtime.activate("sample_feature", "user-1")
    workspace = runtime.create_workspace("sample_feature", "user-1", parent)

    assert first is second
    assert workspace.label == "workspace"
    assert workspace.feature_id == "sample_feature"
    assert workspace.actor_id == "user-1"
    assert workspace.parent is parent
    assert runtime.loaded_feature_ids() == ("sample_feature",)
    assert feature_manager.actors == [
        ("sample_feature", "user-1"),
        ("sample_feature", "user-1"),
        ("sample_feature", "user-1"),
    ]
    runtime.shutdown_all()
    assert runtime.loaded_feature_ids() == ()


def test_lifecycle_event_unloads_feature(tmp_path: Path) -> None:
    record = _record(tmp_path)
    events = EventBus()
    runtime = FeatureRuntimeManager(
        feature_manager=_FeatureManager(record),
        services=ServiceRegistry().provider,
        event_bus=events,
    )
    runtime.activate("sample_feature", "user-1")
    events.publish(ApplicationEvent("feature.disabled", {"feature_id": "sample_feature"}))
    assert runtime.loaded_feature_ids() == ()
    runtime.shutdown_all()


def test_descriptor_mismatch_is_rejected_and_modules_are_cleaned(tmp_path: Path) -> None:
    record = _record(tmp_path)
    plugin_path = tmp_path / "plugin.py"
    source = plugin_path.read_text(encoding="utf-8").replace("'Sample', 'Test feature'", "'Tampered', 'Test feature'")
    plugin_path.write_text(source, encoding="utf-8")
    runtime = FeatureRuntimeManager(
        feature_manager=_FeatureManager(record),
        services=ServiceRegistry().provider,
        event_bus=EventBus(),
    )

    with pytest.raises(ApplicationError) as error:
        runtime.activate("sample_feature", "user-1")
    assert error.value.code == "FEATURE_DESCRIPTOR_MISMATCH"
    assert runtime.loaded_feature_ids() == ()
    runtime.shutdown_all()


def test_invalid_entry_point_is_rejected(tmp_path: Path) -> None:
    record = _record(tmp_path)
    object.__setattr__(record.manifest, "entry_point", "../outside:BadClass")
    runtime = FeatureRuntimeManager(
        feature_manager=_FeatureManager(record),
        services=ServiceRegistry().provider,
        event_bus=EventBus(),
    )
    with pytest.raises(ApplicationError) as error:
        runtime.activate("sample_feature", "user-1")
    assert error.value.code == "FEATURE_ENTRY_POINT_INVALID"
    runtime.shutdown_all()


def test_activation_requires_feature_manager_authorization(tmp_path: Path) -> None:
    record = _record(tmp_path)

    class DeniedFeatureManager(_FeatureManager):
        def get_enabled_feature(self, feature_id: str, actor_id: str) -> FeatureRecord:
            raise ApplicationError("AUTH_PERMISSION_DENIED", "Not authorized.")

    runtime = FeatureRuntimeManager(
        feature_manager=DeniedFeatureManager(record),
        services=ServiceRegistry().provider,
        event_bus=EventBus(),
    )
    with pytest.raises(ApplicationError) as error:
        runtime.activate("sample_feature", "user-without-permission")
    assert error.value.code == "AUTH_PERMISSION_DENIED"
    assert runtime.loaded_feature_ids() == ()
    runtime.shutdown_all()


def test_workspace_instance_must_match_manifest_declaration(tmp_path: Path) -> None:
    record = _record(tmp_path)
    plugin_path = tmp_path / "plugin.py"
    source = plugin_path.read_text(encoding="utf-8").replace(
        "return SampleWorkspace(LABEL, context.feature_id, context.actor_id, context.parent)",
        "return object()",
    )
    plugin_path.write_text(source, encoding="utf-8")
    runtime = FeatureRuntimeManager(
        feature_manager=_FeatureManager(record),
        services=ServiceRegistry().provider,
        event_bus=EventBus(),
    )
    with pytest.raises(ApplicationError) as error:
        runtime.create_workspace("sample_feature", "user-1", object())
    assert error.value.code == "FEATURE_WORKSPACE_INVALID"
    assert runtime.loaded_feature_ids() == ("sample_feature",)
    runtime.shutdown_all()


def test_module_symlink_cannot_escape_package_root(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    outside_module = tmp_path / "outside.py"
    outside_module.write_text("class Outside: pass\n", encoding="utf-8")
    try:
        (package_root / "plugin.py").symlink_to(outside_module)
    except OSError:
        pytest.skip("The current platform does not permit creating symbolic links.")
    record = _record(package_root)
    runtime = FeatureRuntimeManager(
        feature_manager=_FeatureManager(record),
        services=ServiceRegistry().provider,
        event_bus=EventBus(),
    )
    with pytest.raises(ApplicationError) as error:
        runtime.activate("sample_feature", "user-1")
    assert error.value.code == "FEATURE_ENTRY_POINT_INVALID"
    assert runtime.loaded_feature_ids() == ()
    runtime.shutdown_all()


def test_failed_initialization_calls_shutdown_and_cleans_modules(tmp_path: Path) -> None:
    record = _record(tmp_path)
    marker = tmp_path / "shutdown-called.txt"
    plugin_path = tmp_path / "plugin.py"
    source = plugin_path.read_text(encoding="utf-8")
    source = source.replace(
        "def initialize(self, context): self.context = context",
        "def initialize(self, context): raise RuntimeError('initialization failure')",
    ).replace(
        "def shutdown(self): self.closed = True",
        f"def shutdown(self): open({str(marker)!r}, 'w', encoding='utf-8').write('yes')",
    )
    plugin_path.write_text(source, encoding="utf-8")
    runtime = FeatureRuntimeManager(
        feature_manager=_FeatureManager(record),
        services=ServiceRegistry().provider,
        event_bus=EventBus(),
    )
    with pytest.raises(ApplicationError) as error:
        runtime.activate("sample_feature", "user-1")
    assert error.value.code == "FEATURE_LOAD_FAILED"
    assert marker.read_text(encoding="utf-8") == "yes"
    assert runtime.loaded_feature_ids() == ()
    runtime.shutdown_all()


def test_incomplete_feature_module_contract_is_rejected(tmp_path: Path) -> None:
    record = _record(tmp_path)
    plugin_path = tmp_path / "plugin.py"
    source = plugin_path.read_text(encoding="utf-8").replace(
        "    def execute(self, request): return request\n", ""
    )
    plugin_path.write_text(source, encoding="utf-8")
    runtime = FeatureRuntimeManager(
        feature_manager=_FeatureManager(record),
        services=ServiceRegistry().provider,
        event_bus=EventBus(),
    )
    with pytest.raises(ApplicationError) as error:
        runtime.activate("sample_feature", "user-1")
    assert error.value.code == "FEATURE_CONTRACT_INVALID"
    assert runtime.loaded_feature_ids() == ()
    runtime.shutdown_all()


def test_feature_service_provider_exposes_only_declared_dependencies(tmp_path: Path) -> None:
    services = ServiceRegistry()
    allowed_service = object()
    services.register("shared.allowed", allowed_service, version="1.0.0")
    record = _record(
        tmp_path,
        dependencies=FeatureDependencies(services=(ServiceDependency("shared.allowed", "1.x"),)),
    )
    runtime = FeatureRuntimeManager(
        feature_manager=_FeatureManager(record),
        services=services.provider,
        event_bus=EventBus(),
    )
    instance = runtime.activate("sample_feature", "user-1")
    assert instance.context.services.get("shared.allowed", "1.x") is allowed_service
    with pytest.raises(ApplicationError) as error:
        instance.context.services.get("shared.undeclared")
    assert error.value.code == "FEATURE_SERVICE_NOT_DECLARED"
    runtime.shutdown_all()
