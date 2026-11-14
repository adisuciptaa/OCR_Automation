"""Application-level Feature Manager implementation; never imports feature code."""
from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app import API_CONTRACT_VERSION, __version__ as CORE_VERSION
from app.core.event_bus import ApplicationEvent, EventBus
from app.core.exceptions import ApplicationError, ServiceUnavailableError
from app.core.service_registry import ServiceProvider
from app.feature_manager.contracts import (
    AuthorizationService, FeatureHealthCheckService, FeatureRegistryRepository,
    FeatureRollbackService,
)
from app.feature_manager.installer import FeatureInstaller
from app.feature_manager.lifecycle_manager import FeatureLifecycleManager
from app.feature_manager.manifest_loader import ManifestLoader
from app.feature_manager.models import (
    FeatureDependency, FeatureDescriptor, FeatureRecord, FeatureState, PackageCandidate,
    PackageValidationResult,
)
from app.feature_manager.package_verifier import PackageVerifier
from app.feature_manager.registry import FeatureRegistry
from app.feature_manager.updater import FeatureUpdater
from app.feature_manager.uninstaller import FeatureUninstaller


def _version(value: str) -> tuple[object, ...]:
    try:
        normalized = value.split("+", 1)[0]
        release, separator, prerelease = normalized.partition("-")
        major, minor, patch = (int(part) for part in release.split("."))
        if not separator:
            return major, minor, patch, 1, ()
        identifiers = tuple(
            (0, int(item)) if item.isdigit() else (1, item)
            for item in prerelease.split(".")
        )
        return major, minor, patch, 0, identifiers
    except (ValueError, TypeError):
        return (0, 0, 0, 0, ())


def _version_matches(actual: str, requested: str) -> bool:
    actual_parts = actual.split(".")
    requested_parts = requested.split(".")
    if len(requested_parts) == 2 and requested_parts[1] == "x":
        return actual_parts[0] == requested_parts[0]
    if len(requested_parts) == 3 and requested_parts[2] == "x":
        return actual_parts[:2] == requested_parts[:2]
    return actual == requested


class FeatureManagerService:
    def __init__(self, *, feature_root: Path, repository: FeatureRegistryRepository,
                 authorization: AuthorizationService, service_provider: ServiceProvider,
                 event_bus: EventBus, verifier: PackageVerifier,
                 license_check: Callable[[str | None], bool] | None = None,
                 has_active_jobs: Callable[[str], bool] | None = None,
                 backup_root: Path | None = None, quarantine_root: Path | None = None,
                 health_check_manager: FeatureHealthCheckService | None = None,
                 rollback_coordinator: FeatureRollbackService | None = None,
                 logger: logging.Logger | None = None) -> None:
        self.feature_root = feature_root.resolve()
        self.repository = FeatureRegistry(repository)
        self.authorization = authorization
        self.service_provider = service_provider
        self.event_bus = event_bus
        self.verifier = verifier
        self.loader = ManifestLoader()
        self.license_check = license_check if license_check is not None else (lambda entitlement: entitlement is None)
        self.has_active_jobs = has_active_jobs or (lambda _feature_id: False)
        self.backup_root = backup_root or self.feature_root.parent / "backups" / "features"
        self.quarantine_root = quarantine_root or self.feature_root.parent / "quarantine" / "packages"
        self.health_check_manager = health_check_manager
        self.rollback_coordinator = rollback_coordinator
        self.logger = logger or logging.getLogger(__name__)

    def install_archive(self, archive_path: str, actor_id: str) -> FeatureRecord:
        self.authorization.require(actor_id, "feature.install")
        installer = FeatureInstaller(
            self.feature_root.parent / "packages", self.feature_root, self.loader, self.verifier
        )
        candidate: PackageCandidate | None = None
        try:
            candidate = installer.stage_archive(archive_path)
            validation = self.validate(candidate)
            if not validation.valid:
                raise ApplicationError(
                    validation.errors[0], "Feature package failed validation.",
                    details={"errors": validation.errors},
                )
            installed_path = installer.commit(candidate)
            installed_candidate = PackageCandidate(
                installed_path, installed_path / "manifest.json", candidate.manifest,
                candidate.package_digest,
            )
            try:
                return self.register(installed_candidate, actor_id)
            except Exception:
                shutil.rmtree(installed_path, ignore_errors=True)
                raise
        except ApplicationError as exc:
            quarantine_errors = {
                "FEATURE_MANIFEST_INVALID", "FEATURE_PACKAGE_INVALID", "FEATURE_PACKAGE_PATH_INVALID",
                "FEATURE_SIGNATURE_INVALID", "FEATURE_CORE_INCOMPATIBLE", "FEATURE_DEPENDENCY_MISSING",
                "FEATURE_DEPENDENCY_INCOMPATIBLE", "FEATURE_DEPENDENCY_CYCLE", "FEATURE_ENTRY_POINT_INVALID",
            }
            if exc.code in quarantine_errors:
                self._quarantine_archive(Path(archive_path), exc.code)
            raise
        finally:
            if candidate is not None:
                stage_root = candidate.package_path
                staging_parent = self.feature_root.parent / "packages" / ".staging"
                if stage_root.exists() and stage_root.is_relative_to(staging_parent.resolve()):
                    shutil.rmtree(
                        stage_root.parent if stage_root.parent != staging_parent else stage_root,
                        ignore_errors=True,
                    )

    def _quarantine_archive(self, archive_path: Path, error_code: str) -> None:
        try:
            if not archive_path.is_file() or archive_path.is_symlink():
                return
            if archive_path.stat().st_size > 128 * 1024 * 1024:
                self.logger.warning("Rejected oversized feature archive; quarantine copy skipped.")
                return
            self.quarantine_root.mkdir(parents=True, exist_ok=True)
            destination = self.quarantine_root / f"{uuid4()}-{archive_path.name}.quarantined"
            shutil.copy2(archive_path, destination)
            self.logger.warning(
                "Feature archive copied to quarantine: error_code=%s quarantine_id=%s",
                error_code, destination.name,
            )
        except OSError:
            self.logger.exception("Unable to preserve rejected feature archive in quarantine.")

    def discover(self) -> tuple[PackageCandidate, ...]:
        from app.feature_manager.discovery import FeatureDiscovery
        return FeatureDiscovery(self.feature_root, self.loader, self.verifier).discover()

    def validate(self, candidate: PackageCandidate) -> PackageValidationResult:
        errors: list[str] = []
        manifest = candidate.manifest
        try:
            on_disk_manifest = self.loader.load(candidate.package_path)
            package_root = candidate.package_path.resolve(strict=True)
            expected_manifest_path = package_root / "manifest.json"
            if candidate.manifest_path.resolve(strict=False) != expected_manifest_path:
                errors.append("FEATURE_MANIFEST_INVALID")
            if dict(on_disk_manifest.raw) != dict(manifest.raw):
                errors.append("FEATURE_MANIFEST_INVALID")
            if not package_root.is_dir():
                errors.append("FEATURE_PACKAGE_PATH_INVALID")
            digest = self.verifier.verify(manifest.feature_id, candidate.package_path)
            if digest != candidate.package_digest:
                errors.append("FEATURE_SIGNATURE_INVALID")
        except ApplicationError as exc:
            errors.append(exc.code)
            digest = candidate.package_digest
        except OSError:
            errors.append("FEATURE_PACKAGE_PATH_INVALID")
            digest = candidate.package_digest
        if manifest.minimum_core_version and _version(CORE_VERSION) < _version(manifest.minimum_core_version):
            errors.append("FEATURE_CORE_INCOMPATIBLE")
        if manifest.maximum_core_version and _version(CORE_VERSION) > _version(manifest.maximum_core_version):
            errors.append("FEATURE_CORE_INCOMPATIBLE")
        if _version(manifest.api_contract_version)[0] != _version(API_CONTRACT_VERSION)[0]:
            errors.append("FEATURE_CORE_INCOMPATIBLE")
        if self._has_dependency_cycle(manifest.feature_id, manifest.dependencies.features):
            errors.append("FEATURE_DEPENDENCY_CYCLE")
        for dependency in manifest.dependencies.features:
            installed = self.repository.get(dependency.feature_id)
            if installed is None or installed.state is not FeatureState.ENABLED:
                errors.append("FEATURE_DEPENDENCY_MISSING")
            elif not _version_matches(installed.manifest.version, dependency.version):
                errors.append("FEATURE_DEPENDENCY_INCOMPATIBLE")
        for dependency in manifest.dependencies.services:
            try:
                self.service_provider.get(dependency.service_id, dependency.version)
            except ServiceUnavailableError:
                errors.append("FEATURE_DEPENDENCY_MISSING")
        # Verify that the declared entry-point module is package-relative and exists.
        module_name = manifest.entry_point.split(":", 1)[0]
        module_path = candidate.package_path.joinpath(*module_name.split("."))
        resolved_module = module_path.resolve(strict=False)
        if not resolved_module.is_relative_to(candidate.package_path.resolve()):
            errors.append("FEATURE_ENTRY_POINT_INVALID")
        elif not (module_path.with_suffix(".py").is_file() or (module_path / "__init__.py").is_file()):
            errors.append("FEATURE_ENTRY_POINT_INVALID")
        return PackageValidationResult(not errors, manifest.feature_id, digest, tuple(dict.fromkeys(errors)))

    def register(self, candidate: PackageCandidate, actor_id: str) -> FeatureRecord:
        self.authorization.require(actor_id, "feature.install")
        validation = self.validate(candidate)
        if not validation.valid:
            code = validation.errors[0]
            self._audit(actor_id, candidate.manifest.feature_id, "register", None, None,
                        candidate.package_digest, "rejected", code)
            raise ApplicationError(code, "Feature package failed validation.", details={"errors": validation.errors})
        package_root = candidate.package_path.resolve(strict=True)
        if not package_root.is_relative_to(self.feature_root):
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Registration package must be inside the approved feature root.")
        existing = self.repository.get(candidate.manifest.feature_id)
        if existing and existing.state is not FeatureState.UNINSTALLED:
            raise ApplicationError("FEATURE_ALREADY_REGISTERED", "Feature is already registered.")
        now = datetime.now(UTC)
        record = FeatureRecord(candidate.manifest, str(candidate.package_path.resolve()),
            candidate.package_digest, "verified", FeatureState.REGISTERED,
            existing.installed_at if existing else now, now)
        self.repository.save(record)
        self._emit(actor_id, "feature.registered", record)
        self._audit(actor_id, record.feature_id, "register", existing.state.value if existing else None,
                    record.state.value, record.package_digest, "success")
        return record

    def _has_license_entitlement(self, entitlement: str | None) -> bool:
        """Return whether a feature's optional license entitlement is satisfied.

        A missing entitlement means the feature is not license-gated. Custom license
        providers are consulted only for explicitly declared entitlement identifiers.
        """
        if entitlement is None:
            return True
        return self.license_check(entitlement)

    def enable(self, feature_id: str, actor_id: str) -> FeatureRecord:
        self.authorization.require(actor_id, f"feature.configure.{feature_id}")
        record = self._require_record(feature_id)
        if record.state not in {FeatureState.REGISTERED, FeatureState.DISABLED}:
            raise ApplicationError("FEATURE_LIFECYCLE_INVALID", "Feature cannot be enabled from its current state.")
        self._verify_record_package(record)
        self._check_dependencies(record)
        if not self._has_license_entitlement(record.manifest.license_entitlement):
            raise ApplicationError("FEATURE_LICENSE_INVALID", "Required feature license entitlement is unavailable.")
        updated = self._replace_state(record, FeatureState.ENABLED)
        self.repository.save(updated)
        self._emit(actor_id, "feature.enabled", updated)
        self._audit(actor_id, feature_id, "enable", record.state.value, updated.state.value,
                    updated.package_digest, "success")
        return updated

    def disable(self, feature_id: str, actor_id: str) -> FeatureRecord:
        self.authorization.require(actor_id, f"feature.configure.{feature_id}")
        record = self._require_record(feature_id)
        if record.state is not FeatureState.ENABLED:
            raise ApplicationError("FEATURE_LIFECYCLE_INVALID", "Only enabled features can be disabled.")
        if self.has_active_jobs(feature_id):
            raise ApplicationError("FEATURE_BUSY", "Feature has active jobs and cannot be disabled yet.")
        dependents = self._enabled_dependents(feature_id)
        if dependents:
            raise ApplicationError("FEATURE_HAS_DEPENDENTS", "Feature is required by another enabled feature.",
                                   details={"dependents": dependents})
        updated = self._replace_state(record, FeatureState.DISABLED)
        self.repository.save(updated)
        self._emit(actor_id, "feature.disabled", updated)
        self._audit(actor_id, feature_id, "disable", record.state.value, updated.state.value,
                    updated.package_digest, "success")
        return updated

    def update(self, feature_id: str, package_path: str, actor_id: str) -> FeatureRecord:
        self.authorization.require(actor_id, "feature.update")
        current = self._require_record(feature_id)
        if current.state not in {FeatureState.ENABLED, FeatureState.DISABLED}:
            raise ApplicationError("FEATURE_LIFECYCLE_INVALID", "Feature cannot be updated from its current state.")
        if self.has_active_jobs(feature_id):
            raise ApplicationError("FEATURE_BUSY", "Feature has active jobs and cannot be updated.")
        candidate_source = Path(package_path)
        if candidate_source.is_symlink():
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Update package root cannot be a symbolic link.")
        try:
            candidate_root = candidate_source.resolve(strict=True)
        except OSError as exc:
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Update package directory is unavailable.") from exc
        manifest = self.loader.load(candidate_root)
        if manifest.feature_id != feature_id:
            raise ApplicationError("FEATURE_ID_MISMATCH", "Update package must retain the installed feature_id.")
        if _version(manifest.version) <= _version(current.manifest.version):
            raise ApplicationError("FEATURE_VERSION_NOT_NEWER", "Update package version must be newer.")
        if manifest.data_schema_version != current.manifest.data_schema_version:
            raise ApplicationError(
                "FEATURE_MIGRATION_REQUIRED",
                "Data schema changes require a migration implementation before update.",
            )
        if not self._has_license_entitlement(manifest.license_entitlement):
            raise ApplicationError("FEATURE_LICENSE_INVALID", "Updated feature license entitlement is unavailable.")
        for dependent in self.repository.list_all():
            if dependent.state is FeatureState.ENABLED:
                for dependency in dependent.manifest.dependencies.features:
                    if dependency.feature_id == feature_id and not _version_matches(
                        manifest.version, dependency.version
                    ):
                        raise ApplicationError(
                            "FEATURE_DEPENDENCY_INCOMPATIBLE",
                            "The update would break an enabled dependent feature.",
                            details={"dependent_feature_id": dependent.feature_id},
                        )
        digest = self.verifier.verify(feature_id, candidate_root)
        candidate = PackageCandidate(candidate_root, candidate_root / "manifest.json", manifest, digest)
        validation = self.validate(candidate)
        if not validation.valid:
            raise ApplicationError(validation.errors[0], "Update package failed validation.", details={"errors": validation.errors})
        previous_state = current.state
        self._verify_record_package(current)
        checkpoint_id: str | None = None
        if self.health_check_manager is not None and self.rollback_coordinator is not None:
            checkpoint_id = self.rollback_coordinator.create_checkpoint(feature_id, actor_id)
        pending = self._replace_state(current, FeatureState.UPDATE_PENDING)
        self.repository.save(pending)
        target = Path(current.package_path).resolve()
        updater = FeatureUpdater(self.backup_root)
        backup_path: Path | None = None
        try:
            backup_path = updater.replace_package(
                feature_id=feature_id, old_version=current.manifest.version, target=target,
                candidate_root=candidate_root, expected_digest=digest,
                previous_digest=current.package_digest,
            )
            updated = FeatureRecord(manifest, str(target), digest, "verified", previous_state,
                                    current.installed_at, datetime.now(UTC))
            self.repository.save(updated)
            if self.health_check_manager is not None:
                report = self.health_check_manager.check_feature(feature_id, actor_id)
                if getattr(getattr(report, "status", None), "value", None) != "healthy":
                    raise ApplicationError(
                        "FEATURE_HEALTH_CHECK_FAILED",
                        "Updated feature failed its post-update health check.",
                        details={"feature_id": feature_id},
                    )
            if checkpoint_id is not None:
                self.rollback_coordinator.complete_checkpoint(checkpoint_id, actor_id)
        except Exception:
            if checkpoint_id is not None:
                try:
                    self.rollback_coordinator.rollback(checkpoint_id, actor_id)
                except Exception as rollback_error:
                    self.logger.exception("Automatic feature rollback failed: feature_id=%s", feature_id)
                    raise ApplicationError(
                        "FEATURE_ROLLBACK_FAILED",
                        "Feature update failed and automatic rollback also failed; manual recovery is required.",
                        details={"feature_id": feature_id, "checkpoint_id": checkpoint_id},
                    ) from rollback_error
            else:
                if backup_path is not None and backup_path.exists():
                    updater.restore_backup(target=target, backup=backup_path, feature_id=feature_id)
                rollback = self._replace_state(pending, previous_state)
                self.repository.save(rollback)
            raise
        self._emit(actor_id, "feature.updated", updated)
        self._audit(actor_id, feature_id, "update", previous_state.value, updated.state.value, digest, "success")
        return updated

    def uninstall(self, feature_id: str, actor_id: str) -> FeatureRecord:
        self.authorization.require(actor_id, "feature.uninstall")
        record = self._require_record(feature_id)
        if record.state not in {FeatureState.REGISTERED, FeatureState.DISABLED, FeatureState.ERROR}:
            raise ApplicationError("FEATURE_LIFECYCLE_INVALID", "Feature must be disabled before uninstall.")
        if self.has_active_jobs(feature_id):
            raise ApplicationError("FEATURE_BUSY", "Feature has active jobs and cannot be uninstalled.")
        dependents = self._enabled_dependents(feature_id)
        if dependents:
            raise ApplicationError("FEATURE_HAS_DEPENDENTS", "Feature is required by another enabled feature.",
                                   details={"dependents": dependents})
        source_path = Path(record.package_path)
        if source_path.is_symlink():
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Registered package root cannot be a symbolic link.")
        source = source_path.resolve()
        if not source.is_relative_to(self.feature_root):
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Registered package path is outside the feature root.")
        pending = self._replace_state(record, FeatureState.UNINSTALL_PENDING)
        self.repository.save(pending)
        uninstaller = FeatureUninstaller(self.backup_root)
        retained_path: Path | None = None
        try:
            retained_path = uninstaller.retain_package(
                package_path=source, feature_id=feature_id, version=record.manifest.version,
                expected_digest=record.package_digest,
            )
            updated = self._replace_state(pending, FeatureState.UNINSTALLED)
            self.repository.save(updated)
        except Exception:
            if retained_path is not None and retained_path.exists() and not source.exists():
                retained_path.replace(source)
            rollback = self._replace_state(pending, record.state)
            self.repository.save(rollback)
            raise
        self._emit(actor_id, "feature.uninstalled", updated)
        self._audit(actor_id, feature_id, "uninstall", record.state.value, updated.state.value,
                    record.package_digest, "success")
        return updated

    def get_enabled_feature(self, feature_id: str, user_id: str) -> FeatureRecord:
        """Return a freshly verified, enabled feature record for runtime activation."""
        record = self._require_record(feature_id)
        if record.state is not FeatureState.ENABLED or record.signature_status != "verified":
            raise ApplicationError("FEATURE_NOT_AVAILABLE", "Feature is not enabled and verified.")
        self.authorization.require(user_id, f"feature.view.{feature_id}")
        self._verify_record_package(record)
        self._check_dependencies(record)
        if not self._has_license_entitlement(record.manifest.license_entitlement):
            raise ApplicationError("FEATURE_LICENSE_INVALID", "Required feature license entitlement is unavailable.")
        return record

    def list_available(self, user_id: str) -> tuple[FeatureDescriptor, ...]:
        available: list[FeatureDescriptor] = []
        for record in self.repository.list_all():
            if record.state is not FeatureState.ENABLED or record.signature_status != "verified":
                continue
            try:
                self._verify_record_package(record)
                self._check_dependencies(record)
                if not self._has_license_entitlement(record.manifest.license_entitlement):
                    continue
                if self.authorization.is_allowed(user_id, f"feature.view.{record.feature_id}"):
                    available.append(FeatureDescriptor(record.feature_id, record.manifest.display_name,
                        record.manifest.description, record.manifest.version, record.manifest.icon,
                        record.manifest.permissions, record.manifest.license_entitlement))
            except ApplicationError:
                self.logger.warning("Feature omitted from catalog after validation: %s", record.feature_id)
        return tuple(available)

    def _check_dependencies(self, record: FeatureRecord) -> None:
        for dependency in record.manifest.dependencies.features:
            installed = self.repository.get(dependency.feature_id)
            if installed is None or installed.state is not FeatureState.ENABLED:
                raise ApplicationError("FEATURE_DEPENDENCY_MISSING", "A required feature is not enabled.")
            if not _version_matches(installed.manifest.version, dependency.version):
                raise ApplicationError("FEATURE_DEPENDENCY_INCOMPATIBLE", "A required feature version is incompatible.")
        for dependency in record.manifest.dependencies.services:
            try:
                service = self.service_provider.get(dependency.service_id, dependency.version)
            except ServiceUnavailableError as exc:
                raise ApplicationError("FEATURE_DEPENDENCY_MISSING", "A required service is unavailable.") from exc
            # Provider contract exposes object, not registry metadata. Service versions are checked by provider.
            if service is None:
                raise ApplicationError("FEATURE_DEPENDENCY_MISSING", "A required service is unavailable.")

    def _verify_record_package(self, record: FeatureRecord) -> None:
        package_path = Path(record.package_path)
        if package_path.is_symlink():
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Registered package root cannot be a symbolic link.")
        try:
            path = package_path.resolve(strict=True)
        except OSError as exc:
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Registered package directory is unavailable.") from exc
        if not path.is_relative_to(self.feature_root):
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Registered package path is outside the feature root.")
        digest = self.verifier.verify(record.feature_id, path)
        if digest != record.package_digest:
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Installed package integrity has changed.")
        disk_manifest = self.loader.load(path)
        if dict(disk_manifest.raw) != dict(record.manifest.raw):
            raise ApplicationError(
                "FEATURE_MANIFEST_INVALID",
                "Registered feature metadata does not match the verified package manifest.",
            )

    def _has_dependency_cycle(self, feature_id: str, candidate_dependencies: tuple[FeatureDependency, ...]) -> bool:
        graph = {
            record.feature_id: tuple(item.feature_id for item in record.manifest.dependencies.features)
            for record in self.repository.list_all()
        }
        graph[feature_id] = tuple(item.feature_id for item in candidate_dependencies)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for child in graph.get(node, ()):
                if visit(child):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        return visit(feature_id)

    def _enabled_dependents(self, feature_id: str) -> list[str]:
        return [record.feature_id for record in self.repository.list_all()
                if record.state is FeatureState.ENABLED and any(
                    dependency.feature_id == feature_id for dependency in record.manifest.dependencies.features
                )]

    def _require_record(self, feature_id: str) -> FeatureRecord:
        record = self.repository.get(feature_id)
        if record is None:
            raise ApplicationError("FEATURE_NOT_FOUND", "Feature is not registered.")
        return record

    @staticmethod
    def _replace_state(record: FeatureRecord, state: FeatureState) -> FeatureRecord:
        FeatureLifecycleManager.transition(record.state, state)
        return FeatureRecord(record.manifest, record.package_path, record.package_digest,
            record.signature_status, state, record.installed_at, datetime.now(UTC), record.last_error_code)

    def _emit(self, actor_id: str, event_name: str, record: FeatureRecord) -> None:
        self.event_bus.publish(ApplicationEvent(event_name, {
            "feature_id": record.feature_id, "state": record.state.value,
            "version": record.manifest.version, "package_digest": record.package_digest,
        }, actor_id=actor_id))

    def _audit(self, actor_id: str, feature_id: str, operation: str, previous: str | None,
               resulting: str | None, digest: str | None, result: str, error_code: str | None = None) -> None:
        audit = getattr(self.repository, "audit", None)
        if callable(audit):
            audit(actor_id=actor_id, feature_id=feature_id, operation=operation,
                  previous_state=previous, resulting_state=resulting, package_digest=digest,
                  result=result, error_code=error_code)
