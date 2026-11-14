from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import ApplicationError
from app.feature_manager.package_verifier import PackageVerifier
from app.feature_manager.uninstaller import FeatureUninstaller
from app.feature_manager.updater import FeatureUpdater


def _write_package(path: Path, content: str) -> None:
    path.mkdir()
    (path / "plugin.py").write_text(content, encoding="utf-8")


def test_updater_restores_original_when_new_package_digest_fails(tmp_path):
    target = tmp_path / "features" / "sample_reader"
    target.parent.mkdir()
    _write_package(target, "old")
    candidate = tmp_path / "candidate"
    _write_package(candidate, "new")
    old_digest = PackageVerifier.digest_directory(target)
    updater = FeatureUpdater(tmp_path / "backups")

    with pytest.raises(ApplicationError):
        updater.replace_package(
            feature_id="sample_reader", old_version="1.0.0", target=target,
            candidate_root=candidate, expected_digest="sha256:" + "0" * 64,
            previous_digest=old_digest,
        )
    assert (target / "plugin.py").read_text(encoding="utf-8") == "old"
    assert not (target.parent / ".sample_reader.updating").exists()


def test_uninstaller_retains_verified_package_before_removal(tmp_path):
    package = tmp_path / "features" / "sample_reader"
    package.parent.mkdir()
    _write_package(package, "trusted")
    digest = PackageVerifier.digest_directory(package)
    retained = FeatureUninstaller(tmp_path / "backups").retain_package(
        package_path=package, feature_id="sample_reader", version="1.0.0",
        expected_digest=digest,
    )
    assert retained is not None
    assert not package.exists()
    assert PackageVerifier.digest_directory(retained) == digest
