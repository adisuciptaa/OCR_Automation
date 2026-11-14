"""Trusted feature runtime loading, activation, and resource lifecycle management.

Feature packages execute in-process with the application's OS privileges. Package
integrity and authorization are checked before every activation; this is not a sandbox.
"""
from __future__ import annotations

import importlib
import logging
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from app.core.event_bus import EventBus
from app.core.exceptions import ApplicationError, ServiceUnavailableError
from app.core.service_registry import ServiceProvider
from app.feature_manager.models import FeatureDescriptor, FeatureRecord
from app.feature_manager.runtime_contracts import FeatureContext, UIContext

_MODULE_PART = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class _FeatureServiceProvider:
    """Restricts feature service resolution to manifest-declared dependencies."""

    def __init__(self, provider: ServiceProvider, declared_service_ids: tuple[str, ...]) -> None:
        self._provider = provider
        self._declared_service_ids = frozenset(declared_service_ids)

    def get(self, service_id: str, version: str | None = None) -> object:
        if service_id not in self._declared_service_ids:
            raise ServiceUnavailableError(
                "FEATURE_SERVICE_NOT_DECLARED",
                "Feature attempted to access a service not declared in its manifest.",
                details={"service_id": service_id},
            )
        return self._provider.get(service_id, version)


@dataclass(slots=True)
class _LoadedFeature:
    record: FeatureRecord
    module_prefix: str
    module: ModuleType
    instance: object
    workspace_class: type


class FeatureRuntimeManager:
    """Loads verified feature entry points and manages one live instance per feature."""

    def __init__(
        self,
        *,
        feature_manager: object,
        services: ServiceProvider,
        event_bus: EventBus,
        logger: logging.Logger | None = None,
    ) -> None:
        self._feature_manager = feature_manager
        self._services = services
        self._event_bus = event_bus
        self._logger = logger or logging.getLogger(__name__)
        self._loaded: dict[str, _LoadedFeature] = {}
        self._lock = threading.RLock()
        self._unsubscribe = tuple(
            event_bus.subscribe(name, self._on_feature_lifecycle_event)
            for name in ("feature.disabled", "feature.updated", "feature.uninstalled")
        )

    def activate(self, feature_id: str, actor_id: str) -> object:
        """Return an initialized feature module after fresh registry/security checks."""
        with self._lock:
            record = self._feature_manager.get_enabled_feature(feature_id, actor_id)
            loaded = self._loaded.get(feature_id)
            if loaded is not None:
                if loaded.record.package_digest == record.package_digest:
                    return loaded.instance
                self._shutdown_locked(feature_id)
            return self._load_locked(record)

    def create_workspace(self, feature_id: str, actor_id: str, parent: object) -> object:
        """Create a workspace only through the approved FeatureModule contract."""
        with self._lock:
            instance = self.activate(feature_id, actor_id)
            create_workspace = getattr(instance, "create_workspace", None)
            if not callable(create_workspace):
                raise ApplicationError(
                    "FEATURE_WORKSPACE_INVALID",
                    "Feature does not implement the required workspace contract.",
                )
            workspace = create_workspace(UIContext(parent, actor_id, feature_id))
            loaded = self._loaded.get(feature_id)
            if loaded is None or not isinstance(workspace, loaded.workspace_class):
                raise ApplicationError(
                    "FEATURE_WORKSPACE_INVALID",
                    "Feature workspace does not match the class declared in its manifest.",
                )
            return workspace

    def unload(self, feature_id: str) -> None:
        with self._lock:
            self._shutdown_locked(feature_id)

    def shutdown_all(self) -> None:
        with self._lock:
            for feature_id in tuple(self._loaded):
                self._shutdown_locked(feature_id)
            for unsubscribe in self._unsubscribe:
                unsubscribe()

    def loaded_feature_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._loaded))

    def _load_locked(self, record: FeatureRecord) -> object:
        try:
            package_root = Path(record.package_path).resolve(strict=True)
        except OSError as exc:
            raise ApplicationError(
                "FEATURE_PACKAGE_PATH_INVALID", "Feature package directory is unavailable."
            ) from exc
        entry_module, class_name = self._parse_target(record.manifest.entry_point)
        workspace_module, workspace_class_name = self._parse_target(
            record.manifest.workspace, "FEATURE_WORKSPACE_INVALID"
        )
        self._resolve_module_file(package_root, entry_module, "FEATURE_ENTRY_POINT_INVALID")
        self._resolve_module_file(package_root, workspace_module, "FEATURE_WORKSPACE_INVALID")

        digest_token = record.package_digest.rsplit(":", 1)[-1][:16]
        prefix = f"_ocr_feature_{record.feature_id}_{digest_token}"
        instance: object | None = None
        try:
            namespace = ModuleType(prefix)
            namespace.__path__ = [str(package_root)]  # type: ignore[attr-defined]
            namespace.__package__ = prefix
            namespace.__file__ = str(package_root)
            sys.modules[prefix] = namespace
            module = importlib.import_module(f"{prefix}.{entry_module}")
            workspace_module_object = importlib.import_module(f"{prefix}.{workspace_module}")
            feature_class = getattr(module, class_name, None)
            workspace_class = getattr(workspace_module_object, workspace_class_name, None)
            if not isinstance(feature_class, type):
                raise ApplicationError(
                    "FEATURE_ENTRY_POINT_INVALID", "Feature entry point class was not found."
                )
            if not isinstance(workspace_class, type):
                raise ApplicationError(
                    "FEATURE_WORKSPACE_INVALID", "Manifest-declared workspace class was not found."
                )
            instance = feature_class()
            self._validate_feature_contract(instance)
            self._validate_descriptor(instance, record)
            initialize = getattr(instance, "initialize", None)
            if not callable(initialize):
                raise ApplicationError(
                    "FEATURE_CONTRACT_INVALID", "Feature does not implement initialize(context)."
                )
            declared_services = tuple(
                dependency.service_id for dependency in record.manifest.dependencies.services
            )
            initialize(FeatureContext(
                _FeatureServiceProvider(self._services, declared_services),
                self._event_bus,
                logging.LoggerAdapter(self._logger, {"feature_id": record.feature_id}),
                record.feature_id,
            ))
            self._loaded[record.feature_id] = _LoadedFeature(
                record, prefix, module, instance, workspace_class
            )
            self._logger.info("Feature runtime activated: feature_id=%s", record.feature_id)
            return instance
        except ApplicationError:
            self._shutdown_instance(instance, record.feature_id)
            self._remove_modules(prefix)
            raise
        except Exception as exc:
            self._shutdown_instance(instance, record.feature_id)
            self._remove_modules(prefix)
            self._logger.exception("Feature runtime activation failed: feature_id=%s", record.feature_id)
            raise ApplicationError(
                "FEATURE_LOAD_FAILED", "Feature could not be initialized."
            ) from exc

    @staticmethod
    def _resolve_module_file(package_root: Path, module_name: str, error_code: str) -> Path:
        module_path = package_root.joinpath(*module_name.split("."))
        source_file = module_path.with_suffix(".py")
        package_file = module_path / "__init__.py"
        try:
            resolved = (
                source_file.resolve(strict=True)
                if source_file.is_file()
                else package_file.resolve(strict=True)
            )
        except OSError as exc:
            raise ApplicationError(error_code, "Declared feature module is missing.") from exc
        if not resolved.is_file() or not resolved.is_relative_to(package_root):
            raise ApplicationError(error_code, "Declared feature module is outside its package or missing.")
        return resolved

    @staticmethod
    def _parse_target(
        target: str, error_code: str = "FEATURE_ENTRY_POINT_INVALID"
    ) -> tuple[str, str]:
        if not isinstance(target, str) or target.count(":") != 1:
            raise ApplicationError(error_code, "Feature target must use module:Class format.")
        module_name, class_name = target.split(":", 1)
        parts = module_name.split(".")
        if not parts or not all(_MODULE_PART.fullmatch(part) for part in parts) or not _MODULE_PART.fullmatch(class_name):
            raise ApplicationError(error_code, "Feature target contains invalid identifiers.")
        return module_name, class_name

    @staticmethod
    def _validate_feature_contract(instance: object) -> None:
        required_methods = (
            "initialize", "get_descriptor", "create_workspace",
            "validate_configuration", "execute", "shutdown",
        )
        missing = tuple(
            name for name in required_methods if not callable(getattr(instance, name, None))
        )
        if missing:
            raise ApplicationError(
                "FEATURE_CONTRACT_INVALID",
                "Feature does not implement the complete public FeatureModule contract.",
                details={"missing_methods": missing},
            )

    @staticmethod
    def _validate_descriptor(instance: object, record: FeatureRecord) -> None:
        get_descriptor = getattr(instance, "get_descriptor", None)
        if not callable(get_descriptor):
            raise ApplicationError("FEATURE_CONTRACT_INVALID", "Feature does not implement get_descriptor().")
        descriptor = get_descriptor()
        expected = FeatureDescriptor(
            record.feature_id, record.manifest.display_name, record.manifest.description,
            record.manifest.version, record.manifest.icon, record.manifest.permissions,
            record.manifest.license_entitlement,
        )
        if descriptor != expected:
            raise ApplicationError(
                "FEATURE_DESCRIPTOR_MISMATCH", "Runtime feature descriptor does not match its verified manifest."
            )

    def _shutdown_instance(self, instance: object | None, feature_id: str) -> None:
        if instance is None:
            return
        try:
            shutdown = getattr(instance, "shutdown", None)
            if callable(shutdown):
                shutdown()
        except Exception:
            self._logger.exception("Feature cleanup after activation failure failed: feature_id=%s", feature_id)

    def _shutdown_locked(self, feature_id: str) -> None:
        loaded = self._loaded.pop(feature_id, None)
        if loaded is None:
            return
        try:
            shutdown = getattr(loaded.instance, "shutdown", None)
            if callable(shutdown):
                shutdown()
        except Exception:
            self._logger.exception("Feature shutdown failed: feature_id=%s", feature_id)
        finally:
            self._remove_modules(loaded.module_prefix)
            self._logger.info("Feature runtime unloaded: feature_id=%s", feature_id)

    def _on_feature_lifecycle_event(self, event: object) -> None:
        payload = getattr(event, "payload", {})
        feature_id = payload.get("feature_id") if hasattr(payload, "get") else None
        if isinstance(feature_id, str):
            self.unload(feature_id)

    @staticmethod
    def _remove_modules(prefix: str) -> None:
        for name in tuple(sys.modules):
            if name == prefix or name.startswith(f"{prefix}."):
                sys.modules.pop(name, None)
