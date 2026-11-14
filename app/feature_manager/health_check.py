"""Feature health checks for package, dependencies, configuration, and data stores."""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.core.event_bus import ApplicationEvent, EventBus
from app.core.exceptions import ApplicationError, ServiceUnavailableError
from app.core.service_registry import ServiceProvider
from app.feature_manager.configuration_manager import FeatureConfigurationManagerService
from app.feature_manager.contracts import AuthorizationService, FeatureConfigurationRepository, FeatureRegistryRepository
from app.feature_manager.models import (
    FeatureHealthReport, HealthCheckItem, HealthStatus, FeatureState,
)
from app.feature_manager.package_verifier import PackageVerifier


class FeatureHealthCheckManager:
    """Runs deterministic, read-only health checks for an installed feature."""

    def __init__(
        self, *, registry: FeatureRegistryRepository,
        configurations: FeatureConfigurationRepository,
        authorization: AuthorizationService, services: ServiceProvider,
        verifier: PackageVerifier, data_root: Path,
        event_bus: EventBus | None = None, logger: logging.Logger | None = None,
    ) -> None:
        self._registry = registry
        self._configurations = configurations
        self._authorization = authorization
        self._services = services
        self._verifier = verifier
        self._data_root = Path(data_root).resolve()
        self._event_bus = event_bus
        self._logger = logger or logging.getLogger(__name__)

    def check_feature(self, feature_id: str, actor_id: str) -> FeatureHealthReport:
        self._authorization.require(actor_id, "feature.update", {"feature_id": feature_id})
        record = self._registry.get(feature_id)
        if record is None:
            raise ApplicationError("FEATURE_NOT_FOUND", "Feature is not registered.")
        checks: list[HealthCheckItem] = []
        package_root = Path(record.package_path)
        try:
            if package_root.is_symlink():
                raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Package root is a symbolic link.")
            package_root = package_root.resolve(strict=True)
            digest = self._verifier.verify(feature_id, package_root)
            if digest != record.package_digest:
                raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Installed package digest does not match the registry.")
            raw_manifest = json.loads((package_root / "manifest.json").read_text(encoding="utf-8"))
            if raw_manifest != dict(record.manifest.raw):
                raise ApplicationError("FEATURE_MANIFEST_INVALID", "Installed manifest differs from registered metadata.")
            checks.append(HealthCheckItem("package_integrity", HealthStatus.HEALTHY, "Package digest and manifest are valid."))
        except (OSError, json.JSONDecodeError, ApplicationError) as exc:
            code = getattr(exc, "code", "FEATURE_PACKAGE_INVALID")
            checks.append(HealthCheckItem("package_integrity", HealthStatus.UNHEALTHY, "Package integrity check failed.", code))

        for dependency in record.manifest.dependencies.services:
            try:
                self._services.get(dependency.service_id, dependency.version)
                checks.append(HealthCheckItem(
                    f"service:{dependency.service_id}", HealthStatus.HEALTHY,
                    "Required service is available.",
                ))
            except ServiceUnavailableError as exc:
                checks.append(HealthCheckItem(
                    f"service:{dependency.service_id}", HealthStatus.UNHEALTHY,
                    "Required service is unavailable.", exc.code,
                ))

        for dependency in record.manifest.dependencies.features:
            installed = self._registry.get(dependency.feature_id)
            ok = installed is not None and installed.state is FeatureState.ENABLED
            checks.append(HealthCheckItem(
                f"feature:{dependency.feature_id}",
                HealthStatus.HEALTHY if ok else HealthStatus.UNHEALTHY,
                "Required feature is enabled." if ok else "Required feature is missing or disabled.",
                None if ok else "FEATURE_DEPENDENCY_MISSING",
            ))

        try:
            schema_path = package_root / record.manifest.configuration_schema
            schema_path = schema_path.resolve(strict=True)
            if not schema_path.is_relative_to(package_root):
                raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Configuration schema escapes package root.")
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            FeatureConfigurationManagerService._validate_schema_definition(schema)
            schema_version = FeatureConfigurationManagerService._schema_version(schema)
            for profile in self._configurations.list_for_feature(feature_id):
                if profile.schema_version != schema_version:
                    raise ApplicationError(
                        "FEATURE_CONFIGURATION_MIGRATION_REQUIRED",
                        "A stored configuration profile requires migration.",
                    )
                FeatureConfigurationManagerService._validate_configuration(schema, dict(profile.values))
            checks.append(HealthCheckItem("configuration", HealthStatus.HEALTHY, "Configuration schema and stored profiles are valid."))
        except (OSError, json.JSONDecodeError, ApplicationError, TypeError, ValueError) as exc:
            code = getattr(exc, "code", "FEATURE_CONFIGURATION_INVALID")
            checks.append(HealthCheckItem("configuration", HealthStatus.UNHEALTHY, "Configuration validation failed.", code))

        data_path = self._data_path(feature_id)
        if data_path.exists():
            try:
                with closing(sqlite3.connect(f"file:{data_path.as_posix()}?mode=ro", uri=True)) as connection:
                    row = connection.execute("PRAGMA integrity_check").fetchone()
                    if row is None or row[0] != "ok":
                        raise sqlite3.DatabaseError("Integrity check did not return ok.")
                    schema_table = connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='feature_data_schema'"
                    ).fetchone()
                    if schema_table is None:
                        raise sqlite3.DatabaseError("Feature data schema metadata is missing.")
                    version_row = connection.execute(
                        "SELECT schema_version FROM feature_data_schema WHERE feature_id=?",
                        (feature_id,),
                    ).fetchone()
                    if version_row is None or int(version_row[0]) != record.manifest.data_schema_version:
                        raise sqlite3.DatabaseError("Feature data schema version does not match the installed manifest.")
                checks.append(HealthCheckItem("feature_data", HealthStatus.HEALTHY, "Feature data integrity and schema version are valid."))
            except (sqlite3.Error, ValueError, TypeError):
                checks.append(HealthCheckItem("feature_data", HealthStatus.UNHEALTHY, "Feature data integrity or schema version check failed.", "FEATURE_DATA_INTEGRITY_FAILED"))
        else:
            checks.append(HealthCheckItem("feature_data", HealthStatus.HEALTHY, "No feature data database exists yet."))

        statuses = {item.status for item in checks}
        status = HealthStatus.UNHEALTHY if HealthStatus.UNHEALTHY in statuses else (
            HealthStatus.DEGRADED if HealthStatus.DEGRADED in statuses else HealthStatus.HEALTHY
        )
        report = FeatureHealthReport(feature_id, datetime.now(UTC), status, tuple(checks))
        if self._event_bus is not None:
            self._event_bus.publish(ApplicationEvent(
                "feature.health_checked",
                {"feature_id": feature_id, "status": status.value,
                 "failed_checks": tuple(item.check_id for item in checks if item.status is HealthStatus.UNHEALTHY)},
                actor_id=actor_id,
            ))
        return report

    def _data_path(self, feature_id: str) -> Path:
        if not feature_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_" for char in feature_id):
            raise ApplicationError("FEATURE_ID_INVALID", "Feature identifier is invalid.")
        candidate = self._data_root / f"{feature_id}.sqlite3"
        if candidate.is_symlink():
            raise ApplicationError("FEATURE_DATA_PATH_INVALID", "Feature data path cannot be a symbolic link.")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._data_root):
            raise ApplicationError("FEATURE_DATA_PATH_INVALID", "Feature data path escapes its root.")
        return resolved
