"""Non-destructive package retention for feature uninstall operations."""
from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.core.exceptions import ApplicationError
from app.feature_manager.package_verifier import PackageVerifier


class FeatureUninstaller:
    def __init__(self, backup_root: Path) -> None:
        self._backup_root = backup_root

    def retain_package(
        self, *, package_path: Path, feature_id: str, version: str, expected_digest: str
    ) -> Path | None:
        if not package_path.exists():
            return None
        self._backup_root.mkdir(parents=True, exist_ok=True)
        retained = self._backup_root / f"{feature_id}-{version}-uninstalled"
        if retained.exists():
            suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            retained = retained.with_name(f"{retained.name}-{suffix}")
        try:
            shutil.copytree(package_path, retained)
            if PackageVerifier.digest_directory(retained) != expected_digest:
                shutil.rmtree(retained, ignore_errors=True)
                raise ApplicationError(
                    "FEATURE_SIGNATURE_INVALID", "Feature package changed while preparing uninstall backup."
                )
            shutil.rmtree(package_path)
        except ApplicationError:
            raise
        except OSError as exc:
            raise ApplicationError(
                "FEATURE_UNINSTALL_FAILED", "Feature package could not be safely retained."
            ) from exc
        return retained
