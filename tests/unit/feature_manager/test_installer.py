from __future__ import annotations

import json
import zipfile

import pytest

from app.core.exceptions import ApplicationError
from app.feature_manager.installer import FeatureInstaller
from app.feature_manager.manifest_loader import ManifestLoader
from app.feature_manager.package_verifier import PackageVerifier


def _source_package(root):
    root.mkdir()
    data = {
        "manifest_schema_version": "1.0", "feature_id": "sample_reader", "display_name": "Sample",
        "version": "1.0.0", "description": "Sample", "publisher": "OCR Automation",
        "entry_point": "plugin:SampleFeature", "minimum_core_version": "0.1.0",
        "maximum_core_version": None, "api_contract_version": "2.1.0",
        "dependencies": {"features": [], "services": []}, "permissions": [],
        "configuration_schema": "config_schema.json",
        "ui": {"navigation_label": "Sample", "icon": "file", "workspace": "ui:Sample"},
        "license_entitlement": None, "data_schema_version": 1,
    }
    (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    (root / "config_schema.json").write_text('{"type":"object"}', encoding="utf-8")
    (root / "plugin.py").write_text("class SampleFeature: pass", encoding="utf-8")


def test_installer_stages_and_commits_verified_package(tmp_path):
    source = tmp_path / "source"
    _source_package(source)
    digest = PackageVerifier.digest_directory(source)
    installer = FeatureInstaller(tmp_path / "packages", tmp_path / "features", ManifestLoader(),
                                 PackageVerifier({"sample_reader": digest}))
    archive = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in source.iterdir():
            bundle.write(path, path.name)
    candidate = installer.stage_archive(archive)
    installed = installer.commit(candidate)
    assert installed.is_dir()
    assert PackageVerifier.digest_directory(installed) == digest


def test_installer_rejects_zip_path_traversal(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "bad")
    installer = FeatureInstaller(tmp_path / "packages", tmp_path / "features", ManifestLoader(), PackageVerifier())
    with pytest.raises(ApplicationError):
        installer.stage_archive(archive)
