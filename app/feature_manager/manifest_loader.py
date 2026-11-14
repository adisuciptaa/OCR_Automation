"""Strict manifest parsing and package-relative path validation."""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from app.core.exceptions import ApplicationError
from app.feature_manager.models import FeatureDependencies, FeatureDependency, FeatureManifest, ServiceDependency

_FEATURE_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_DEPENDENCY_VERSION = re.compile(r"^(?:\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?|\d+\.x|\d+\.\d+\.x)$")
_ENTRY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$")
_KNOWN_TOP = {
    "manifest_schema_version", "feature_id", "display_name", "version", "description",
    "publisher", "entry_point", "minimum_core_version", "maximum_core_version",
    "api_contract_version", "dependencies", "permissions", "configuration_schema", "ui",
    "license_entitlement", "data_schema_version", "publisher_id",
}


class ManifestLoader:
    def load(self, package_root: Path) -> FeatureManifest:
        if package_root.is_symlink():
            self._invalid("Feature package root cannot be a symbolic link.")
        try:
            root = package_root.resolve(strict=True)
        except OSError as exc:
            raise ApplicationError("FEATURE_PACKAGE_PATH_INVALID", "Feature package directory is unavailable.") from exc
        manifest_path = root / "manifest.json"
        if manifest_path.is_symlink():
            self._invalid("Manifest file cannot be a symbolic link.")
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApplicationError("FEATURE_MANIFEST_INVALID", "Feature manifest could not be read.") from exc
        if not isinstance(raw, dict):
            self._invalid("Manifest root must be a JSON object.")
        schema_path = Path(__file__).parent / "schemas" / "manifest.schema.json"
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApplicationError("FEATURE_MANIFEST_SCHEMA_UNAVAILABLE", "Feature manifest schema is unavailable.") from exc
        self._validate_schema_value(raw, schema, "manifest")
        unknown = set(raw) - _KNOWN_TOP
        if unknown:
            self._invalid(f"Unknown manifest fields: {', '.join(sorted(unknown))}.")
        required = _KNOWN_TOP - {"maximum_core_version", "license_entitlement", "publisher_id"}
        missing = required - set(raw)
        if missing:
            self._invalid(f"Missing manifest fields: {', '.join(sorted(missing))}.")

        if raw["manifest_schema_version"] != "1.0":
            self._invalid("Unsupported manifest_schema_version.")
        feature_id = self._string(raw, "feature_id")
        if not _FEATURE_ID.fullmatch(feature_id):
            self._invalid("feature_id must use lowercase snake_case.")
        for key in ("version", "minimum_core_version", "api_contract_version"):
            value = self._string(raw, key)
            if not _VERSION.fullmatch(value):
                self._invalid(f"{key} must use semantic version format.")
        if raw.get("maximum_core_version") is not None and not _VERSION.fullmatch(raw["maximum_core_version"]):
            self._invalid("maximum_core_version must use semantic version format or null.")
        if not _ENTRY.fullmatch(self._string(raw, "entry_point")):
            self._invalid("entry_point must use module:Class format.")

        deps = raw["dependencies"]
        if not isinstance(deps, dict) or set(deps) != {"features", "services"}:
            self._invalid("dependencies must contain features and services arrays.")
        if not isinstance(deps["features"], list):
            self._invalid("Feature dependencies must be an array.")
        features: list[FeatureDependency] = []
        for item in deps["features"]:
            if not isinstance(item, dict) or set(item) != {"id", "version"}:
                self._invalid("Each feature dependency requires id and version.")
            if not isinstance(item["id"], str) or not _FEATURE_ID.fullmatch(item["id"]):
                self._invalid("Feature dependency IDs must use lowercase snake_case.")
            if not isinstance(item["version"], str) or not _DEPENDENCY_VERSION.fullmatch(item["version"]):
                self._invalid("Feature dependency version must be semantic or a supported wildcard.")
            features.append(FeatureDependency(item["id"], item["version"]))
        if not isinstance(deps["services"], list):
            self._invalid("Service dependencies must be an array.")
        services: list[ServiceDependency] = []
        for item in deps["services"]:
            if not isinstance(item, dict) or set(item) != {"id", "version"}:
                self._invalid("Each service dependency requires id and version.")
            if not isinstance(item["id"], str) or not item["id"].strip():
                self._invalid("Service dependency ID must be non-empty.")
            if not isinstance(item["version"], str) or not _DEPENDENCY_VERSION.fullmatch(item["version"]):
                self._invalid("Service dependency version must be semantic or a supported wildcard.")
            services.append(ServiceDependency(item["id"], item["version"]))
        permissions = raw["permissions"]
        if not isinstance(permissions, list) or not all(isinstance(x, str) and x.strip() for x in permissions):
            self._invalid("permissions must be an array of non-empty strings.")
        ui = raw["ui"]
        if not isinstance(ui, dict) or set(ui) != {"navigation_label", "icon", "workspace"}:
            self._invalid("ui must contain navigation_label, icon, and workspace.")
        for key in ("navigation_label", "icon", "workspace"):
            if not isinstance(ui[key], str) or not ui[key].strip():
                self._invalid(f"ui.{key} must be a non-empty string.")
        schema_path = self._safe_package_file(root, self._string(raw, "configuration_schema"))
        if schema_path.is_symlink():
            self._invalid("Configuration schema cannot be a symbolic link.")
        if not schema_path.is_file():
            self._invalid("Configuration schema file does not exist.")
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApplicationError("FEATURE_MANIFEST_INVALID", "Configuration schema is invalid JSON.") from exc
        if not isinstance(schema, dict) or schema.get("type") != "object":
            self._invalid("Configuration schema must define an object at its root.")
        data_version = raw["data_schema_version"]
        if isinstance(data_version, bool) or not isinstance(data_version, int) or data_version < 1:
            self._invalid("data_schema_version must be a positive integer.")
        return FeatureManifest(
            manifest_schema_version=self._string(raw, "manifest_schema_version"),
            feature_id=feature_id, display_name=self._string(raw, "display_name"),
            version=self._string(raw, "version"), description=self._string(raw, "description"),
            publisher=self._string(raw, "publisher"), entry_point=raw["entry_point"],
            minimum_core_version=raw["minimum_core_version"],
            maximum_core_version=raw.get("maximum_core_version"),
            api_contract_version=raw["api_contract_version"],
            dependencies=FeatureDependencies(tuple(features), tuple(services)),
            permissions=tuple(permissions), configuration_schema=raw["configuration_schema"],
            navigation_label=ui["navigation_label"], icon=ui["icon"], workspace=ui["workspace"],
            license_entitlement=raw.get("license_entitlement"), data_schema_version=data_version,
            raw=raw, publisher_id=raw.get("publisher_id"),
        )

    @classmethod
    def _validate_schema_value(cls, value: Any, schema: dict[str, Any], location: str) -> None:
        expected = schema.get("type")
        allowed_types = expected if isinstance(expected, list) else [expected]
        type_map = {"object": dict, "array": list, "string": str, "integer": int}
        if allowed_types and not any(
            (candidate == "null" and value is None)
            or (candidate == "integer" and isinstance(value, int) and not isinstance(value, bool))
            or (candidate in type_map and isinstance(value, type_map[candidate]))
            for candidate in allowed_types
        ):
            cls._invalid(f"{location} has an invalid JSON type.")
        if "const" in schema and value != schema["const"]:
            cls._invalid(f"{location} has an unsupported value.")
        if isinstance(value, str):
            if len(value) < schema.get("minLength", 0):
                cls._invalid(f"{location} is shorter than permitted.")
            pattern = schema.get("pattern")
            if pattern and not re.fullmatch(pattern, value):
                cls._invalid(f"{location} has an invalid format.")
        if isinstance(value, int) and not isinstance(value, bool) and value < schema.get("minimum", value):
            cls._invalid(f"{location} is below the permitted minimum.")
        if isinstance(value, dict):
            required = schema.get("required", [])
            missing = set(required) - set(value)
            if missing:
                cls._invalid(f"{location} is missing required fields: {', '.join(sorted(missing))}.")
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False and set(value) - set(properties):
                cls._invalid(f"{location} contains unsupported fields.")
            for key, child in value.items():
                if key in properties:
                    cls._validate_schema_value(child, properties[key], f"{location}.{key}")
        if isinstance(value, list):
            if schema.get("uniqueItems") and len(value) != len({json.dumps(item, sort_keys=True) for item in value}):
                cls._invalid(f"{location} contains duplicate items.")
            item_schema = schema.get("items")
            if item_schema:
                for index, item in enumerate(value):
                    cls._validate_schema_value(item, item_schema, f"{location}[{index}]")

    @staticmethod
    def _string(raw: dict[str, Any], key: str) -> str:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            ManifestLoader._invalid(f"{key} must be a non-empty string.")
        return value.strip()

    @staticmethod
    def _safe_package_file(root: Path, relative: str) -> Path:
        pure = PurePosixPath(relative)
        if (
            pure.is_absolute()
            or ".." in pure.parts
            or "\\" in relative
            or "\x00" in relative
            or (pure.parts and ":" in pure.parts[0])
        ):
            ManifestLoader._invalid("Package paths must remain inside the package root.")
        target = (root / Path(*pure.parts)).resolve(strict=False)
        if not target.is_relative_to(root):
            ManifestLoader._invalid("Package path escapes the package root.")
        return target

    @staticmethod
    def _invalid(message: str) -> None:
        raise ApplicationError("FEATURE_MANIFEST_INVALID", message)
