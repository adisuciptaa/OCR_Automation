"""Safe staging and installation of trusted feature ZIP packages."""
from __future__ import annotations

import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from app.core.exceptions import ApplicationError
from app.feature_manager.manifest_loader import ManifestLoader
from app.feature_manager.models import PackageCandidate
from app.feature_manager.package_verifier import PackageVerifier

_MAX_FILES = 2_000
_MAX_UNCOMPRESSED = 256 * 1024 * 1024
_MAX_ARCHIVE_BYTES = 128 * 1024 * 1024


class FeatureInstaller:
    def __init__(self, packages_root: Path, features_root: Path,
                 loader: ManifestLoader, verifier: PackageVerifier) -> None:
        self._packages = packages_root
        self._features = features_root
        self._loader = loader
        self._verifier = verifier

    def stage_archive(self, archive_path: Path | str) -> PackageCandidate:
        try:
            archive = Path(archive_path).resolve(strict=True)
        except OSError as exc:
            raise ApplicationError("FEATURE_PACKAGE_INVALID", "Feature archive is unavailable.") from exc
        if archive.stat().st_size > _MAX_ARCHIVE_BYTES:
            raise ApplicationError("FEATURE_PACKAGE_INVALID", "Feature archive exceeds compressed-size limits.")
        self._packages.mkdir(parents=True, exist_ok=True)
        stage_parent = self._packages / ".staging"
        stage_parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix="feature-", dir=stage_parent))
        try:
            with zipfile.ZipFile(archive) as bundle:
                infos = bundle.infolist()
                if len(infos) > _MAX_FILES or sum(item.file_size for item in infos) > _MAX_UNCOMPRESSED:
                    raise ApplicationError("FEATURE_PACKAGE_INVALID", "Feature archive exceeds package limits.")
                for info in infos:
                    name = info.filename.replace("\\", "/")
                    relative = PurePosixPath(name)
                    mode = info.external_attr >> 16
                    if relative.is_absolute() or ".." in relative.parts or not relative.parts or ":" in relative.parts[0] or "\x00" in name:
                        raise ApplicationError("FEATURE_PACKAGE_INVALID", "Feature archive contains an unsafe path.")
                    if stat.S_ISLNK(mode):
                        raise ApplicationError("FEATURE_PACKAGE_INVALID", "Feature archive cannot contain symbolic links.")
                    target = (stage / Path(*relative.parts)).resolve()
                    if not target.is_relative_to(stage.resolve()):
                        raise ApplicationError("FEATURE_PACKAGE_INVALID", "Feature archive path escapes staging directory.")
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with bundle.open(info) as source, target.open("xb") as destination:
                            shutil.copyfileobj(source, destination)
            roots = [stage]
            if not (stage / "manifest.json").is_file():
                children = [item for item in stage.iterdir() if item.is_dir()]
                if len(children) == 1 and (children[0] / "manifest.json").is_file():
                    roots = children
                else:
                    raise ApplicationError("FEATURE_MANIFEST_INVALID", "Archive must contain one feature package root.")
            package_root = roots[0]
            manifest = self._loader.load(package_root)
            digest = self._verifier.verify(manifest.feature_id, package_root)
            return PackageCandidate(package_root, package_root / "manifest.json", manifest, digest)
        except ApplicationError:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            shutil.rmtree(stage, ignore_errors=True)
            raise ApplicationError(
                "FEATURE_PACKAGE_INVALID", "Feature archive could not be safely extracted."
            ) from exc
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    def commit(self, candidate: PackageCandidate) -> Path:
        destination = self._features / candidate.manifest.feature_id
        self._features.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise ApplicationError("FEATURE_ALREADY_INSTALLED", "Feature package is already installed.")
        staged_copy = self._features / f".{candidate.manifest.feature_id}.installing"
        if staged_copy.is_symlink():
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Installation staging path cannot be a symbolic link.")
        if staged_copy.exists():
            shutil.rmtree(staged_copy)
        shutil.copytree(candidate.package_path, staged_copy)
        if PackageVerifier.digest_directory(staged_copy) != candidate.package_digest:
            shutil.rmtree(staged_copy, ignore_errors=True)
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Package changed during installation.")
        staged_copy.replace(destination)
        return destination
