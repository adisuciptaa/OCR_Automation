from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.core.exceptions import ApplicationError
from app.feature_manager.configuration_manager import FeatureConfigurationManagerService
from app.feature_manager.models import (
    ConfigurationScope, FeatureDependencies, FeatureManifest, FeatureRecord, FeatureState,
)
from app.persistence.repositories.feature_configuration_repository import SQLiteFeatureConfigurationRepository
from app.feature_manager.package_verifier import PackageVerifier
from app.persistence.repositories.feature_registry_repository import SQLiteFeatureRegistryRepository


class AllowAuthorization:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[tuple[str, str]] = []

    def require(self, actor_id: str, permission: str, resource: object | None = None) -> None:
        self.calls.append((actor_id, permission))
        if not self.allowed:
            raise ApplicationError("AUTH_PERMISSION_DENIED", "Denied")

    def is_allowed(self, actor_id: str, permission: str, resource: object | None = None) -> bool:
        return self.allowed


def _manager(tmp_path, *, allowed: bool = True, schema: dict | None = None):
    package = tmp_path / "features" / "sample_reader"
    package.mkdir(parents=True)
    schema = schema or {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object", "x-config-version": 2,
        "properties": {"language": {"type": "string", "default": "id", "enum": ["id", "en"]},
                       "dpi": {"type": "integer", "minimum": 100, "maximum": 600, "default": 300}},
        "required": ["language", "dpi"], "additionalProperties": False,
    }
    (package / "config_schema.json").write_text(json.dumps(schema), encoding="utf-8")
    raw = {
        "manifest_schema_version": "1.0", "feature_id": "sample_reader", "display_name": "Sample",
        "version": "1.0.0", "description": "Sample", "publisher": "Publisher",
        "entry_point": "plugin:Sample", "minimum_core_version": "0.1.0", "api_contract_version": "2.3.0",
        "dependencies": {"features": [], "services": []}, "permissions": [],
        "configuration_schema": "config_schema.json",
        "ui": {"navigation_label": "Sample", "icon": "file", "workspace": "ui:Sample"},
        "data_schema_version": 1,
    }
    manifest = FeatureManifest("1.0", "sample_reader", "Sample", "1.0.0", "Sample", "Publisher",
        "plugin:Sample", "0.1.0", "2.3.0", FeatureDependencies(), (), "config_schema.json",
        "Sample", "file", "ui:Sample", 1, raw=raw)
    now = datetime.now(UTC)
    digest = PackageVerifier.digest_directory(package)
    record = FeatureRecord(manifest, str(package), digest, "verified", FeatureState.ENABLED, now, now)
    registry = SQLiteFeatureRegistryRepository(tmp_path / "db.sqlite3")
    registry.save(record)
    repository = SQLiteFeatureConfigurationRepository(tmp_path / "db.sqlite3")
    authorization = AllowAuthorization(allowed)
    service = FeatureConfigurationManagerService(registry=registry, configurations=repository,
        authorization=authorization)
    return service, repository, authorization


def test_get_returns_schema_defaults_and_installation_scope(tmp_path):
    service, _, auth = _manager(tmp_path)
    result = service.get_configuration("sample_reader", "admin", ConfigurationScope.INSTALLATION, "")
    assert dict(result.values) == {"language": "id", "dpi": 300}
    assert result.scope_key == "default"
    assert auth.calls == [("admin", "feature.configure.sample_reader")]


def test_save_and_reload_scoped_configuration(tmp_path):
    service, repository, _ = _manager(tmp_path)
    saved = service.save_configuration("sample_reader", "admin", ConfigurationScope.USER,
        "user-123", {"language": "en", "dpi": 400})
    loaded = service.get_configuration("sample_reader", "admin", ConfigurationScope.USER, "user-123")
    assert dict(loaded.values) == {"language": "en", "dpi": 400}
    assert loaded.updated_by == "admin"
    assert repository.list_for_feature("sample_reader") == (saved,)


def test_invalid_configuration_is_rejected_without_persistence(tmp_path):
    service, repository, _ = _manager(tmp_path)
    with pytest.raises(ApplicationError) as error:
        service.save_configuration("sample_reader", "admin", ConfigurationScope.COMPANY,
            "company-1", {"language": "fr", "dpi": 900})
    assert error.value.code == "FEATURE_CONFIGURATION_INVALID"
    assert repository.list_for_feature("sample_reader") == ()


def test_missing_authorization_provider_fails_closed(tmp_path):
    service, repository, _ = _manager(tmp_path)
    service._authorization = None
    with pytest.raises(ApplicationError) as error:
        service.save_configuration("sample_reader", "admin", ConfigurationScope.INSTALLATION,
            "default", {"language": "id", "dpi": 300})
    assert error.value.code == "FEATURE_PERMISSION_DENIED"
    assert repository.list_for_feature("sample_reader") == ()


def test_denied_authorization_blocks_reads_and_writes(tmp_path):
    service, repository, _ = _manager(tmp_path, allowed=False)
    with pytest.raises(ApplicationError):
        service.get_configuration("sample_reader", "operator", ConfigurationScope.INSTALLATION, "default")
    with pytest.raises(ApplicationError):
        service.save_configuration("sample_reader", "operator", ConfigurationScope.INSTALLATION,
            "default", {"language": "id", "dpi": 300})
    assert repository.list_for_feature("sample_reader") == ()


def test_reset_removes_override_and_returns_defaults(tmp_path):
    service, repository, _ = _manager(tmp_path)
    service.save_configuration("sample_reader", "admin", ConfigurationScope.COMPANY,
        "company-1", {"language": "en", "dpi": 400})
    reset = service.reset_configuration("sample_reader", "admin", ConfigurationScope.COMPANY, "company-1")
    assert dict(reset.values) == {"language": "id", "dpi": 300}
    assert repository.get("sample_reader", ConfigurationScope.COMPANY, "company-1") is None


def test_configuration_schema_version_mismatch_requires_migration(tmp_path):
    service, repository, _ = _manager(tmp_path)
    service.save_configuration("sample_reader", "admin", ConfigurationScope.INSTALLATION,
        "default", {"language": "id", "dpi": 300})
    stored = repository.get("sample_reader", ConfigurationScope.INSTALLATION, "default")
    from dataclasses import replace
    repository.save(replace(stored, schema_version=1))
    with pytest.raises(ApplicationError) as error:
        service.get_configuration("sample_reader", "admin", ConfigurationScope.INSTALLATION, "default")
    assert error.value.code == "FEATURE_CONFIGURATION_MIGRATION_REQUIRED"


def test_secret_fields_are_not_saved_in_plain_json_profiles(tmp_path):
    service, repository, _ = _manager(tmp_path, schema={
        "type": "object", "properties": {"token": {"type": "string", "writeOnly": True}}
    })
    with pytest.raises(ApplicationError) as error:
        service.get_configuration("sample_reader", "admin", ConfigurationScope.INSTALLATION, "default")
    assert error.value.code == "FEATURE_CONFIGURATION_SECRET_UNSUPPORTED"
    assert repository.list_for_feature("sample_reader") == ()


def test_invalid_scope_key_is_rejected(tmp_path):
    service, _, _ = _manager(tmp_path)
    with pytest.raises(ApplicationError) as error:
        service.get_configuration("sample_reader", "admin", ConfigurationScope.USER, " ")
    assert error.value.code == "FEATURE_CONFIGURATION_SCOPE_KEY_INVALID"


def test_modified_feature_package_is_rejected_before_schema_use(tmp_path):
    service, _, _ = _manager(tmp_path)
    schema_path = tmp_path / "features" / "sample_reader" / "config_schema.json"
    schema_path.write_text('{"type":"object","properties":{"tampered":{"type":"boolean"}}}', encoding="utf-8")
    with pytest.raises(ApplicationError) as error:
        service.get_configuration("sample_reader", "admin", ConfigurationScope.INSTALLATION, "default")
    assert error.value.code == "FEATURE_SIGNATURE_INVALID"


def test_configuration_mutation_is_audited_and_publishes_event(tmp_path):
    from app.core.event_bus import EventBus

    service, _, _ = _manager(tmp_path)
    events = []
    bus = EventBus()
    bus.subscribe("feature.configuration.updated", events.append)
    service._event_bus = bus
    service.save_configuration("sample_reader", "admin", ConfigurationScope.INSTALLATION,
        "default", {"language": "id", "dpi": 300})
    with service._registry._connect() as connection:
        audit = connection.execute(
            "SELECT operation, result FROM feature_audit WHERE feature_id='sample_reader'"
        ).fetchone()
    assert tuple(audit) == ("configuration.updated", "success")
    assert len(events) == 1
    assert events[0].payload["feature_id"] == "sample_reader"
    assert events[0].payload["scope"] == "installation"


def test_unsupported_schema_keyword_fails_closed(tmp_path):
    service, _, _ = _manager(tmp_path, schema={
        "type": "object", "properties": {"code": {"type": "string", "format": "email"}}
    })
    with pytest.raises(ApplicationError) as error:
        service.get_configuration("sample_reader", "admin", ConfigurationScope.INSTALLATION, "default")
    assert error.value.code == "FEATURE_CONFIGURATION_SCHEMA_UNSUPPORTED"


def test_non_json_configuration_values_are_rejected(tmp_path):
    service, repository, _ = _manager(tmp_path)
    with pytest.raises(ApplicationError) as error:
        service.save_configuration("sample_reader", "admin", ConfigurationScope.INSTALLATION,
            "default", {"language": "id", "dpi": 300, "extra": object()})
    assert error.value.code == "FEATURE_CONFIGURATION_INVALID"
    assert repository.list_for_feature("sample_reader") == ()



def test_get_configuration_schema_returns_validated_read_only_schema(tmp_path):
    service, _, authorization = _manager(tmp_path)
    result = service.get_configuration_schema("sample_reader", "admin")
    assert result.feature_id == "sample_reader"
    assert result.schema_version == 2
    assert result.definition["properties"]["dpi"]["type"] == "integer"
    assert authorization.calls == [("admin", "feature.configure.sample_reader")]
    with pytest.raises(TypeError):
        result.definition["type"] = "array"
