"""Filesystem staging and atomic promotion for feature package updates."""
from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.core.exceptions import ApplicationError
from app.feature_manager.package_verifier import PackageVerifier


class FeatureUpdater:
    def __init__(self, backup_root: Path) -> None:
        self._backup_root = backup_root

    def replace_package(
        self,
        *,
        feature_id: str,
        old_version: str,
        target: Path,
        candidate_root: Path,
        expected_digest: str,
        previous_digest: str,
    ) -> Path:
        self._backup_root.mkdir(parents=True, exist_ok=True)
        suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self._backup_root / f"{feature_id}-{old_version}-{suffix}"
        staged = target.with_name(f".{target.name}.updating")
        previous = target.with_name(f".{target.name}.previous")
        try:
            shutil.copytree(target, backup)
            if PackageVerifier.digest_directory(backup) != previous_digest:
                raise ApplicationError(
                    "FEATURE_SIGNATURE_INVALID", "Previous package changed while preparing update backup."
                )
            shutil.copytree(candidate_root, staged)
            if PackageVerifier.digest_directory(staged) != expected_digest:
                raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Update package changed while staging.")
            target.replace(previous)
            try:
                staged.replace(target)
            except Exception:
                previous.replace(target)
                raise
            shutil.rmtree(previous)
            return backup
        except Exception:
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
            if previous.exists():
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                previous.replace(target)
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            raise

    def restore_backup(self, *, target: Path, backup: Path, feature_id: str) -> None:
        if not backup.is_dir():
            raise ApplicationError("FEATURE_ROLLBACK_FAILED", "Previous feature package backup is unavailable.")
        restore_staged = target.with_name(f".{target.name}.rollback")
        if restore_staged.exists():
            shutil.rmtree(restore_staged, ignore_errors=True)
        shutil.copytree(backup, restore_staged)
        if target.exists():
            failed = self._backup_root / (
                f"{feature_id}-failed-update-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
            )
            shutil.copytree(target, failed)
            shutil.rmtree(target)
        restore_staged.replace(target)
