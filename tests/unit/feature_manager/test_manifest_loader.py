from __future__ import annotations

import json

import pytest

from app.core.exceptions import ApplicationError
from app.feature_manager.manifest_loader import ManifestLoader


def _package(tmp_path):
    root = tmp_path / "sample_reader"
    root.mkdir()
    data = {
        "manifest_schema_version": "1.0", "feature_id": "sample_reader",
        "display_name": "Sample Reader", "version": "1.0.0", "description": "Sample",
        "publisher": "OCR Automation", "entry_point": "plugin:SampleFeature",
        "minimum_core_version": "0.1.0", "maximum_core_version": None,
        "api_contract_version": "2.1.0", "dependencies": {"features": [], "services": []},
        "permissions": ["filesystem.read_input"], "configuration_schema": "config_schema.json",
        "ui": {"navigation_label": "Sample", "icon": "file", "workspace": "ui:SampleWorkspace"},
        "license_entitlement": None, "data_schema_version": 1,
    }
    (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    (root / "config_schema.json").write_text('{"type":"object"}', encoding="utf-8")
    (root / "plugin.py").write_text("class SampleFeature: pass\n", encoding="utf-8")
    return root, data


def test_manifest_loader_loads_valid_manifest(tmp_path):
    root, _ = _package(tmp_path)
    manifest = ManifestLoader().load(root)
    assert manifest.feature_id == "sample_reader"
    assert manifest.dependencies.features == ()


def test_manifest_loader_rejects_unknown_fields(tmp_path):
    root, data = _package(tmp_path)
    data["unexpected"] = True
    (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ApplicationError) as error:
        ManifestLoader().load(root)
    assert error.value.code == "FEATURE_MANIFEST_INVALID"


def test_manifest_loader_rejects_path_traversal(tmp_path):
    root, data = _package(tmp_path)
    data["configuration_schema"] = "../outside.json"
    (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ApplicationError):
        ManifestLoader().load(root)
