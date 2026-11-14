"""Typed public models for feature package management."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping
from types import MappingProxyType


class FeatureState(StrEnum):
    DISCOVERED = "discovered"
    VALIDATING = "validating"
    REGISTERED = "registered"
    ENABLED = "enabled"
    DISABLED = "disabled"
    UPDATE_PENDING = "update_pending"
    UNINSTALL_PENDING = "uninstall_pending"
    ERROR = "error"
    QUARANTINED = "quarantined"
    UNINSTALLED = "uninstalled"


@dataclass(frozen=True, slots=True)
class ServiceDependency:
    service_id: str
    version: str


@dataclass(frozen=True, slots=True)
class FeatureDependency:
    feature_id: str
    version: str


@dataclass(frozen=True, slots=True)
class FeatureDependencies:
    features: tuple[FeatureDependency, ...] = ()
    services: tuple[ServiceDependency, ...] = ()


@dataclass(frozen=True, slots=True)
class FeatureManifest:
    manifest_schema_version: str
    feature_id: str
    display_name: str
    version: str
    description: str
    publisher: str
    entry_point: str
    minimum_core_version: str
    api_contract_version: str
    dependencies: FeatureDependencies
    permissions: tuple[str, ...]
    configuration_schema: str
    navigation_label: str
    icon: str
    workspace: str
    data_schema_version: int
    maximum_core_version: str | None = None
    license_entitlement: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
    publisher_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", MappingProxyType(dict(self.raw)))


@dataclass(frozen=True, slots=True)
class PackageCandidate:
    package_path: Path
    manifest_path: Path
    manifest: FeatureManifest
    package_digest: str


@dataclass(frozen=True, slots=True)
class PackageValidationResult:
    valid: bool
    feature_id: str | None
    package_digest: str | None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FeatureRecord:
    manifest: FeatureManifest
    package_path: str
    package_digest: str
    signature_status: str
    state: FeatureState
    installed_at: datetime
    updated_at: datetime
    last_error_code: str | None = None

    @property
    def feature_id(self) -> str:
        return self.manifest.feature_id


@dataclass(frozen=True, slots=True)
class FeatureDescriptor:
    feature_id: str
    display_name: str
    description: str
    version: str
    icon: str
    required_permissions: tuple[str, ...]
    license_entitlement: str | None


class ConfigurationScope(StrEnum):
    INSTALLATION = "installation"
    COMPANY = "company"
    USER = "user"
    JOB = "job"


@dataclass(frozen=True, slots=True)
class FeatureConfiguration:
    feature_id: str
    scope: ConfigurationScope
    scope_key: str
    schema_version: int
    values: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime
    updated_by: str

    def __post_init__(self) -> None:
        import copy
        object.__setattr__(self, "values", MappingProxyType(copy.deepcopy(dict(self.values))))


@dataclass(frozen=True, slots=True)
class FeatureConfigurationSchema:
    """Validated, read-only schema metadata exposed to the Presentation Layer."""

    feature_id: str
    schema_version: int
    definition: Mapping[str, Any]

    def __post_init__(self) -> None:
        import copy
        object.__setattr__(self, "definition", MappingProxyType(copy.deepcopy(dict(self.definition))))


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class HealthCheckItem:
    check_id: str
    status: HealthStatus
    message: str
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class FeatureHealthReport:
    feature_id: str
    checked_at: datetime
    status: HealthStatus
    checks: tuple[HealthCheckItem, ...]


class PublisherStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class PublisherRecord:
    publisher_id: str
    display_name: str
    status: PublisherStatus
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PublisherKeyRecord:
    publisher_id: str
    key_id: str
    public_key_b64: str
    status: str
    created_at: datetime
    revoked_at: datetime | None = None
