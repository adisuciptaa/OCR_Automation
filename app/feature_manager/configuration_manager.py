"""Authorized feature configuration orchestration and JSON Schema validation."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.event_bus import ApplicationEvent, EventBus
from app.core.exceptions import ApplicationError
from app.feature_manager.contracts import AuthorizationService, FeatureConfigurationRepository, FeatureRegistryRepository
from app.feature_manager.models import ConfigurationScope, FeatureConfiguration, FeatureConfigurationSchema, FeatureRecord, FeatureState
from app.feature_manager.package_verifier import PackageVerifier

_ALLOWED_STATES = {FeatureState.REGISTERED, FeatureState.ENABLED, FeatureState.DISABLED}


class FeatureConfigurationManagerService:
    """Owns configuration profiles; Core ConfigManager remains application-global only."""

    def __init__(self, *, registry: FeatureRegistryRepository,
                 configurations: FeatureConfigurationRepository,
                 authorization: AuthorizationService | None,
                 event_bus: EventBus | None = None) -> None:
        self._registry = registry
        self._configurations = configurations
        self._authorization = authorization
        self._event_bus = event_bus

    def get_configuration_schema(self, feature_id: str, actor_id: str) -> FeatureConfigurationSchema:
        """Return validated schema metadata after enforcing the feature configuration permission."""
        self._authorize(feature_id, actor_id)
        record = self._get_feature(feature_id)
        schema = self._load_schema(record)
        return FeatureConfigurationSchema(feature_id, self._schema_version(schema), schema)

    def get_configuration(self, feature_id: str, actor_id: str, scope: ConfigurationScope,
                          scope_key: str) -> FeatureConfiguration:
        self._authorize(feature_id, actor_id)
        record = self._get_feature(feature_id)
        key = self._validate_scope_key(scope, scope_key)
        schema = self._load_schema(record)
        schema_version = self._schema_version(schema)
        stored = self._configurations.get(feature_id, scope, key)
        if stored is not None:
            if stored.schema_version != schema_version:
                raise ApplicationError("FEATURE_CONFIGURATION_MIGRATION_REQUIRED",
                    "Stored feature configuration requires migration before it can be used.",
                    details={"feature_id": feature_id, "stored_schema_version": stored.schema_version,
                             "current_schema_version": schema_version})
            self._validate_configuration(schema, dict(stored.values))
            return stored
        now = datetime.now(UTC)
        return FeatureConfiguration(feature_id, scope, key, schema_version,
            self._defaults(schema), now, now, actor_id)

    def save_configuration(self, feature_id: str, actor_id: str, scope: ConfigurationScope,
                           scope_key: str, values: Mapping[str, object]) -> FeatureConfiguration:
        self._authorize(feature_id, actor_id)
        record = self._get_feature(feature_id)
        key = self._validate_scope_key(scope, scope_key)
        if not isinstance(values, Mapping):
            raise ApplicationError("FEATURE_CONFIGURATION_INVALID", "Configuration must be a JSON object.")
        schema = self._load_schema(record)
        schema_version = self._schema_version(schema)
        normalized = deepcopy(dict(values))
        try:
            json.dumps(normalized, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ApplicationError("FEATURE_CONFIGURATION_INVALID", "Configuration values must be JSON-serializable.") from exc
        self._validate_configuration(schema, normalized)
        now = datetime.now(UTC)
        previous = self._configurations.get(feature_id, scope, key)
        configuration = FeatureConfiguration(feature_id, scope, key, schema_version,
            normalized, previous.created_at if previous else now, now, actor_id)
        self._configurations.save(configuration)
        self._audit(record, actor_id, "configuration.updated", scope, key)
        self._publish("feature.configuration.updated", feature_id, actor_id, scope, key)
        return configuration

    def reset_configuration(self, feature_id: str, actor_id: str, scope: ConfigurationScope,
                            scope_key: str) -> FeatureConfiguration:
        self._authorize(feature_id, actor_id)
        record = self._get_feature(feature_id)
        key = self._validate_scope_key(scope, scope_key)
        schema = self._load_schema(record)
        defaults = self._defaults(schema)
        self._configurations.delete(feature_id, scope, key)
        now = datetime.now(UTC)
        result = FeatureConfiguration(feature_id, scope, key, self._schema_version(schema),
            defaults, now, now, actor_id)
        self._audit(record, actor_id, "configuration.reset", scope, key)
        self._publish("feature.configuration.reset", feature_id, actor_id, scope, key)
        return result

    def _authorize(self, feature_id: str, actor_id: str) -> None:
        if self._authorization is None:
            raise ApplicationError("FEATURE_PERMISSION_DENIED", "Feature configuration is unavailable without authorization.")
        self._authorization.require(actor_id, f"feature.configure.{feature_id}", {"feature_id": feature_id})

    def _get_feature(self, feature_id: str) -> FeatureRecord:
        record = self._registry.get(feature_id)
        if record is None or record.state not in _ALLOWED_STATES:
            raise ApplicationError("FEATURE_NOT_CONFIGURABLE", "The requested feature is not available for configuration.",
                                   details={"feature_id": feature_id})
        return record

    @staticmethod
    def _validate_scope_key(scope: ConfigurationScope, scope_key: str) -> str:
        if not isinstance(scope, ConfigurationScope) or not isinstance(scope_key, str):
            raise ApplicationError("FEATURE_CONFIGURATION_SCOPE_INVALID", "Configuration scope and key are invalid.")
        expected = "default" if scope is ConfigurationScope.INSTALLATION else scope_key.strip() if isinstance(scope_key, str) else ""
        if not expected or (scope is ConfigurationScope.INSTALLATION and scope_key not in {"", "default"}):
            raise ApplicationError("FEATURE_CONFIGURATION_SCOPE_KEY_INVALID", "A valid key is required for this configuration scope.")
        if len(expected) > 200 or "\x00" in expected:
            raise ApplicationError("FEATURE_CONFIGURATION_SCOPE_KEY_INVALID", "Configuration scope key is invalid.")
        return expected

    @staticmethod
    def _load_schema(record: FeatureRecord) -> dict[str, Any]:
        package_path = Path(record.package_path)
        if package_path.is_symlink():
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Feature package path cannot be a symbolic link.")
        try:
            root = package_path.resolve(strict=True)
            actual_digest = PackageVerifier.digest_directory(root)
        except OSError as exc:
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Feature package is unavailable.") from exc
        if actual_digest != record.package_digest:
            raise ApplicationError("FEATURE_SIGNATURE_INVALID", "Feature package integrity has changed since registration.",
                                   details={"feature_id": record.feature_id})
        relative = record.manifest.configuration_schema
        if not isinstance(relative, str) or "\\" in relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Feature configuration schema path is invalid.")
        unresolved_schema_path = root / relative
        if any(part.is_symlink() for part in (unresolved_schema_path, *unresolved_schema_path.parents) if part != root.parent):
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Feature configuration schema cannot traverse symbolic links.")
        try:
            schema_path = unresolved_schema_path.resolve(strict=True)
        except OSError as exc:
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Feature configuration schema is unavailable.") from exc
        if not schema_path.is_relative_to(root) or not schema_path.is_file():
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Feature configuration schema path is unsafe.")
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Feature configuration schema could not be read.") from exc
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Feature configuration schema must define an object root.")
        FeatureConfigurationManagerService._validate_schema_definition(schema)
        if FeatureConfigurationManagerService._contains_secret(schema):
            raise ApplicationError("FEATURE_CONFIGURATION_SECRET_UNSUPPORTED", "Secret fields require a dedicated secure secret store and cannot be stored in feature JSON profiles.")
        return schema

    @classmethod
    def _validate_schema_definition(cls, schema: dict[str, Any]) -> None:
        supported = {
            "$schema", "$id", "title", "description", "default", "type", "properties",
            "required", "additionalProperties", "const", "enum", "minLength", "maxLength",
            "pattern", "minimum", "maximum", "minItems", "maxItems", "uniqueItems", "items",
            "x-config-version", "writeOnly", "x-secret",
        }
        unsupported = set(schema) - supported
        if unsupported:
            raise ApplicationError(
                "FEATURE_CONFIGURATION_SCHEMA_UNSUPPORTED",
                "Feature configuration schema contains unsupported validation keywords.",
                details={"keywords": sorted(unsupported)},
            )
        allowed_types = {"object", "array", "string", "integer", "number", "boolean", "null"}
        declared_type = schema.get("type")
        if declared_type is not None:
            types = declared_type if isinstance(declared_type, list) else [declared_type]
            if not types or any(not isinstance(item, str) or item not in allowed_types for item in types):
                raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Schema type contains an unsupported JSON type.")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict) or any(not isinstance(child, dict) for child in properties.values()):
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Schema properties must be JSON objects.")
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Schema required must be an array of strings.")
        if not isinstance(schema.get("additionalProperties", False), bool):
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_UNSUPPORTED", "Schema additionalProperties must be a boolean.")
        if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Schema enum must be a non-empty array.")
        if "pattern" in schema:
            if not isinstance(schema["pattern"], str):
                raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Schema pattern must be a string.")
            try:
                re.compile(schema["pattern"])
            except re.error as exc:
                raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Schema pattern is invalid.") from exc
        for keyword in ("minLength", "maxLength", "minItems", "maxItems"):
            if keyword in schema and (isinstance(schema[keyword], bool) or not isinstance(schema[keyword], int) or schema[keyword] < 0):
                raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", f"Schema {keyword} must be a non-negative integer.")
        for keyword in ("minimum", "maximum"):
            if keyword in schema and (isinstance(schema[keyword], bool) or not isinstance(schema[keyword], (int, float))):
                raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", f"Schema {keyword} must be numeric.")
        if "uniqueItems" in schema and not isinstance(schema["uniqueItems"], bool):
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Schema uniqueItems must be boolean.")
        for child in properties.values():
            cls._validate_schema_definition(child)
        if "items" in schema:
            if not isinstance(schema["items"], dict):
                raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "Schema items must be an object.")
            cls._validate_schema_definition(schema["items"])

    @staticmethod
    def _contains_secret(schema: Any) -> bool:
        if isinstance(schema, dict):
            if schema.get("writeOnly") is True or schema.get("x-secret") is True:
                return True
            return any(FeatureConfigurationManagerService._contains_secret(value) for value in schema.values())
        if isinstance(schema, list):
            return any(FeatureConfigurationManagerService._contains_secret(value) for value in schema)
        return False

    @classmethod
    def _validate_configuration(cls, schema: dict[str, Any], values: dict[str, Any]) -> None:
        errors: list[str] = []
        cls._validate_node(values, schema, "$", errors)
        if errors:
            raise ApplicationError("FEATURE_CONFIGURATION_INVALID", "Feature configuration does not match its schema.",
                                   details={"validation_errors": errors[:50]})

    @classmethod
    def _validate_node(cls, value: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
        expected = schema.get("type")
        allowed = expected if isinstance(expected, list) else [expected] if expected else []
        type_checks = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str), "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool), "null": lambda v: v is None}
        if allowed and not any(kind in type_checks and type_checks[kind](value) for kind in allowed):
            errors.append(f"{path}: invalid type")
            return
        if "const" in schema and value != schema["const"]:
            errors.append(f"{path}: value must equal const")
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: value is not an allowed option")
        if isinstance(value, dict):
            properties = schema.get("properties", {})
            for name in schema.get("required", []):
                if name not in value:
                    errors.append(f"{path}.{name}: required")
            if schema.get("additionalProperties") is False:
                for name in value.keys() - properties.keys():
                    errors.append(f"{path}.{name}: additional property is not allowed")
            for name, child in value.items():
                if name in properties:
                    cls._validate_node(child, properties[name], f"{path}.{name}", errors)
        elif isinstance(value, str):
            if len(value) < schema.get("minLength", 0):
                errors.append(f"{path}: string is too short")
            if len(value) > schema.get("maxLength", float("inf")):
                errors.append(f"{path}: string is too long")
            if "pattern" in schema and not re.search(schema["pattern"], value):
                errors.append(f"{path}: string format is invalid")
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if value < schema.get("minimum", float("-inf")):
                errors.append(f"{path}: below minimum")
            if value > schema.get("maximum", float("inf")):
                errors.append(f"{path}: above maximum")
        elif isinstance(value, list):
            if len(value) < schema.get("minItems", 0):
                errors.append(f"{path}: too few items")
            if len(value) > schema.get("maxItems", float("inf")):
                errors.append(f"{path}: too many items")
            if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
                errors.append(f"{path}: duplicate items")
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for index, item in enumerate(value):
                    cls._validate_node(item, item_schema, f"{path}[{index}]", errors)


    @staticmethod
    def _schema_version(schema: dict[str, Any]) -> int:
        version = schema.get("x-config-version", 1)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID", "x-config-version must be a positive integer.")
        return version

    @classmethod
    def _defaults(cls, schema: dict[str, Any]) -> dict[str, Any]:
        defaults: dict[str, Any] = {}
        for name, child in schema.get("properties", {}).items():
            if "default" in child:
                default_value = deepcopy(child["default"])
                errors: list[str] = []
                cls._validate_node(default_value, child, f"$.{name}", errors)
                if errors:
                    raise ApplicationError("FEATURE_CONFIGURATION_SCHEMA_INVALID",
                        "Feature configuration schema contains an invalid default value.",
                        details={"validation_errors": errors})
                defaults[name] = default_value
            elif child.get("type") == "object":
                defaults[name] = cls._defaults(child)
        return defaults

    def _audit(self, record, actor_id: str, operation: str, scope: ConfigurationScope, scope_key: str) -> None:
        audit = getattr(self._registry, "audit", None)
        if callable(audit):
            audit(actor_id=actor_id, feature_id=record.feature_id, operation=operation,
                  previous_state=record.state.value, resulting_state=record.state.value,
                  package_digest=record.package_digest, result="success")

    def _publish(self, event_name: str, feature_id: str, actor_id: str,
                 scope: ConfigurationScope, scope_key: str) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(ApplicationEvent(event_name, actor_id=actor_id,
                payload={"feature_id": feature_id, "scope": scope.value}))
