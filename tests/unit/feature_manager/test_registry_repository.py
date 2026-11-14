from __future__ import annotations

from datetime import UTC, datetime

from app.feature_manager.models import FeatureDependencies, FeatureManifest, FeatureRecord, FeatureState
from app.persistence.repositories.feature_registry_repository import SQLiteFeatureRegistryRepository


def test_sqlite_feature_registry_round_trip_and_audit(tmp_path):
    repository = SQLiteFeatureRegistryRepository(tmp_path / "registry.sqlite3")
    raw = {
        "manifest_schema_version": "1.0", "feature_id": "sample_reader", "display_name": "Sample",
        "version": "1.0.0", "description": "Sample", "publisher": "Publisher",
        "entry_point": "plugin:Sample", "minimum_core_version": "0.1.0", "api_contract_version": "2.1.0",
        "dependencies": {"features": [], "services": []}, "permissions": [],
        "configuration_schema": "config_schema.json", "ui": {"navigation_label": "Sample", "icon": "file", "workspace": "ui:Sample"},
        "data_schema_version": 1,
    }
    manifest = FeatureManifest("1.0", "sample_reader", "Sample", "1.0.0", "Sample", "Publisher",
        "plugin:Sample", "0.1.0", "2.1.0", FeatureDependencies(), (), "config_schema.json",
        "Sample", "file", "ui:Sample", 1, raw=raw)
    now = datetime.now(UTC)
    record = FeatureRecord(manifest, str(tmp_path / "features" / "sample_reader"), "sha256:abc",
                           "verified", FeatureState.REGISTERED, now, now)
    repository.save(record)
    loaded = repository.get("sample_reader")
    assert loaded is not None
    assert loaded.manifest.feature_id == "sample_reader"
    assert loaded.state is FeatureState.REGISTERED
    listed = repository.list_all()
    assert len(listed) == 1
    assert listed[0].feature_id == "sample_reader"
    repository.audit(actor_id="admin", feature_id="sample_reader", operation="register",
        previous_state=None, resulting_state="registered", package_digest="sha256:abc", result="success")
    with repository._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM feature_audit").fetchone()[0] == 1
