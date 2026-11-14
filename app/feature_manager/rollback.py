"""Durable feature rollback checkpoints and crash-recovery journal."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.event_bus import ApplicationEvent, EventBus
from app.core.exceptions import ApplicationError
from app.feature_manager.contracts import AuthorizationService, FeatureRegistryRepository
from app.feature_manager.manifest_loader import ManifestLoader
from app.feature_manager.models import FeatureRecord, FeatureState
from app.feature_manager.package_verifier import PackageVerifier


class FeatureRollbackCoordinator:
    """Creates durable checkpoints and restores package/registry state atomically.

    Checkpoints are retained after successful rollback for forensic review. This class
    does not claim to reverse arbitrary feature-side effects outside managed package and
    SQLite data paths.
    """

    def __init__(
        self, *, registry: FeatureRegistryRepository, authorization: AuthorizationService,
        backup_root: Path, verifier: PackageVerifier, event_bus: EventBus | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._registry = registry
        self._authorization = authorization
        self._backup_root = Path(backup_root).resolve()
        self._verifier = verifier
        self._event_bus = event_bus
        self._logger = logger or logging.getLogger(__name__)
        self._backup_root.mkdir(parents=True, exist_ok=True)

    def create_checkpoint(self, feature_id: str, actor_id: str) -> str:
        self._authorization.require(actor_id, "feature.update", {"feature_id": feature_id})
        record = self._registry.get(feature_id)
        if record is None:
            raise ApplicationError("FEATURE_NOT_FOUND", "Feature is not registered.")
        source = Path(record.package_path)
        if source.is_symlink():
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Feature package cannot be a symbolic link.")
        try:
            source = source.resolve(strict=True)
        except OSError as exc:
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Feature package is unavailable.") from exc
        digest = self._verifier.verify(feature_id, source)
        if digest != record.package_digest:
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Feature package does not match the registry.")
        checkpoint_id = str(uuid4())
        checkpoint_dir = self._backup_root / checkpoint_id
        checkpoint_dir.mkdir(parents=False, exist_ok=False)
        package_backup = checkpoint_dir / "package"
        try:
            shutil.copytree(source, package_backup)
            if self._verifier.digest_directory(package_backup) != record.package_digest:
                raise ApplicationError("FEATURE_ROLLBACK_CHECKPOINT_INVALID", "Checkpoint package verification failed.")
            payload = {
                "checkpoint_id": checkpoint_id, "feature_id": feature_id,
                "actor_id": actor_id, "status": "prepared",
                "package_path": str(source), "package_backup": str(package_backup),
                "package_digest": record.package_digest,
                "signature_status": record.signature_status, "state": record.state.value,
                "installed_at": record.installed_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
                "manifest": dict(record.manifest.raw),
                "created_at": datetime.now(UTC).isoformat(),
            }
            self._write_journal(checkpoint_dir / "journal.json", payload)
        except Exception:
            shutil.rmtree(checkpoint_dir, ignore_errors=True)
            raise
        self._audit(actor_id, feature_id, "rollback.checkpoint.created", record.state.value, record.state.value, record.package_digest, "success")
        self._publish("feature.rollback_checkpoint_created", feature_id, actor_id, {"checkpoint_id": checkpoint_id})
        return checkpoint_id

    def complete_checkpoint(self, checkpoint_id: str, actor_id: str) -> None:
        """Mark a successful post-update health check so startup recovery leaves it intact."""
        self._authorization.require(actor_id, "feature.update")
        journal_path = (self._backup_root / checkpoint_id / "journal.json").resolve()
        if not journal_path.is_relative_to(self._backup_root):
            raise ApplicationError("FEATURE_ROLLBACK_CHECKPOINT_INVALID", "Checkpoint path is unsafe.")
        try:
            payload = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApplicationError("FEATURE_ROLLBACK_CHECKPOINT_MISSING", "Rollback checkpoint is unavailable.") from exc
        if payload.get("checkpoint_id") != checkpoint_id or payload.get("status") != "prepared":
            raise ApplicationError("FEATURE_ROLLBACK_CHECKPOINT_INVALID", "Checkpoint is not awaiting completion.")
        payload["status"] = "committed"
        payload["committed_at"] = datetime.now(UTC).isoformat()
        payload["committed_by"] = actor_id
        self._write_journal(journal_path, payload)
        feature_id = str(payload["feature_id"])
        self._audit(actor_id, feature_id, "rollback.checkpoint.committed", None, None,
                    str(payload["package_digest"]), "success")
        self._publish("feature.rollback_checkpoint_committed", feature_id, actor_id,
                      {"checkpoint_id": checkpoint_id})

    def rollback(self, checkpoint_id: str, actor_id: str) -> FeatureRecord:
        self._authorization.require(actor_id, "feature.update")
        return self._restore_checkpoint(checkpoint_id, actor_id)

    def recover_pending(self) -> tuple[str, ...]:
        """Restore every prepared checkpoint after an interrupted update/recovery operation."""
        recovered: list[str] = []
        for journal in sorted(self._backup_root.glob("*/journal.json")):
            try:
                payload = json.loads(journal.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._logger.exception("Unreadable feature recovery journal: %s", journal.name)
                continue
            if payload.get("status") != "prepared":
                continue
            checkpoint_id = payload.get("checkpoint_id")
            if not isinstance(checkpoint_id, str):
                continue
            try:
                self._restore_checkpoint(checkpoint_id, "system.recovery")
                recovered.append(checkpoint_id)
            except ApplicationError:
                self._logger.exception("Feature recovery failed: checkpoint_id=%s", checkpoint_id)
        return tuple(recovered)

    def _restore_checkpoint(self, checkpoint_id: str, actor_id: str) -> FeatureRecord:
        if not checkpoint_id or any(char not in "0123456789abcdef-" for char in checkpoint_id.lower()):
            raise ApplicationError("FEATURE_ROLLBACK_CHECKPOINT_INVALID", "Checkpoint identifier is invalid.")
        checkpoint_dir = (self._backup_root / checkpoint_id).resolve()
        if not checkpoint_dir.is_relative_to(self._backup_root):
            raise ApplicationError("FEATURE_ROLLBACK_CHECKPOINT_INVALID", "Checkpoint path is unsafe.")
        journal_path = checkpoint_dir / "journal.json"
        try:
            payload = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApplicationError("FEATURE_ROLLBACK_CHECKPOINT_MISSING", "Rollback checkpoint is unavailable.") from exc
        if payload.get("checkpoint_id") != checkpoint_id or payload.get("status") not in {"prepared", "committed", "rolled_back"}:
            raise ApplicationError("FEATURE_ROLLBACK_CHECKPOINT_INVALID", "Rollback checkpoint state is invalid.")
        feature_id = payload.get("feature_id")
        current = self._registry.get(feature_id) if isinstance(feature_id, str) else None
        if current is None:
            raise ApplicationError("FEATURE_NOT_FOUND", "Feature is not registered.")
        package_backup = Path(payload["package_backup"])
        package_target = Path(payload["package_path"])
        if package_target.resolve(strict=False) != Path(current.package_path).resolve(strict=False):
            raise ApplicationError("FEATURE_ROLLBACK_FAILED", "Checkpoint target does not match the registered package location.")
        if package_target.is_symlink():
            raise ApplicationError("FEATURE_ROLLBACK_FAILED", "Installed package path cannot be a symbolic link.")
        if package_backup.is_symlink() or not package_backup.is_dir():
            raise ApplicationError("FEATURE_ROLLBACK_FAILED", "Verified package backup is unavailable.")
        backup_root = package_backup.resolve(strict=True)
        if not backup_root.is_relative_to(checkpoint_dir):
            raise ApplicationError("FEATURE_ROLLBACK_FAILED", "Package backup escapes its checkpoint.")
        digest = self._verifier.verify(feature_id, backup_root)
        if digest != payload.get("package_digest"):
            raise ApplicationError("FEATURE_ROLLBACK_FAILED", "Package backup integrity verification failed.")
        manifest = ManifestLoader().load(backup_root)
        if dict(manifest.raw) != payload.get("manifest"):
            raise ApplicationError("FEATURE_ROLLBACK_FAILED", "Backup manifest does not match checkpoint metadata.")
        staged = package_target.with_name(f".{package_target.name}.{checkpoint_id}.rollback")
        failed = checkpoint_dir / "failed-package"
        try:
            if staged.exists():
                shutil.rmtree(staged)
            shutil.copytree(backup_root, staged)
            if self._verifier.digest_directory(staged) != digest:
                raise ApplicationError("FEATURE_ROLLBACK_FAILED", "Staged rollback package failed integrity verification.")
            if package_target.exists():
                if failed.exists():
                    shutil.rmtree(failed)
                shutil.copytree(package_target, failed)
                shutil.rmtree(package_target)
            staged.replace(package_target)
            restored = FeatureRecord(
                manifest, str(package_target), digest, payload["signature_status"],
                FeatureState(payload["state"]), datetime.fromisoformat(payload["installed_at"]),
                datetime.now(UTC), None,
            )
            self._registry.save(restored)
            payload["status"] = "rolled_back"
            payload["rolled_back_at"] = datetime.now(UTC).isoformat()
            payload["rolled_back_by"] = actor_id
            self._write_journal(journal_path, payload)
        except Exception as exc:
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
            if failed.exists() and not package_target.exists():
                shutil.copytree(failed, package_target)
            if isinstance(exc, ApplicationError):
                raise
            raise ApplicationError("FEATURE_ROLLBACK_FAILED", "Feature rollback could not be completed.") from exc
        self._audit(actor_id, feature_id, "rollback", current.state.value, restored.state.value, digest, "success")
        self._publish("feature.rolled_back", feature_id, actor_id, {"checkpoint_id": checkpoint_id, "version": manifest.version})
        return restored

    @staticmethod
    def _write_journal(path: Path, payload: dict[str, object]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _audit(self, actor_id: str, feature_id: str, operation: str, previous: str | None,
               resulting: str | None, digest: str | None, result: str) -> None:
        audit = getattr(self._registry, "audit", None)
        if callable(audit):
            audit(actor_id=actor_id, feature_id=feature_id, operation=operation,
                  previous_state=previous, resulting_state=resulting,
                  package_digest=digest, result=result)

    def _publish(self, name: str, feature_id: str, actor_id: str, payload: dict[str, object]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(ApplicationEvent(name, {"feature_id": feature_id, **payload}, actor_id=actor_id))
