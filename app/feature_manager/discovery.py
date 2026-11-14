"""Discovery of feature package directories from approved roots."""
from __future__ import annotations

import logging
from pathlib import Path

from app.core.exceptions import ApplicationError
from app.feature_manager.manifest_loader import ManifestLoader
from app.feature_manager.models import PackageCandidate
from app.feature_manager.package_verifier import PackageVerifier


class FeatureDiscovery:
    def __init__(self, feature_root: Path, loader: ManifestLoader, verifier: PackageVerifier) -> None:
        self._root = feature_root
        self._loader = loader
        self._verifier = verifier
        self._logger = logging.getLogger(__name__)

    def discover(self) -> tuple[PackageCandidate, ...]:
        if not self._root.exists():
            return ()
        if self._root.is_symlink():
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Feature root cannot be a symbolic link.")
        root = self._root.resolve(strict=True)
        candidates: list[PackageCandidate] = []
        for child in sorted(root.iterdir()):
            if child.is_symlink() or not child.is_dir() or not (child / "manifest.json").is_file():
                continue
            try:
                manifest = self._loader.load(child)
                digest = PackageVerifier.digest_directory(child)
            except ApplicationError as exc:
                self._logger.warning(
                    "Skipping invalid feature package directory: path=%s error_code=%s",
                    child.name, exc.code,
                )
                continue
            candidates.append(
                PackageCandidate(child.resolve(), (child / "manifest.json").resolve(), manifest, digest)
            )
        return tuple(candidates)
