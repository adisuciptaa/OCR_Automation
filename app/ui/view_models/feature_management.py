"""Read-only projection of Feature Registry records for the Feature CMS."""
from __future__ import annotations

from typing import Protocol

from app.feature_manager.models import FeatureRecord


class FeatureManagementProvider(Protocol):
    def list_records(self) -> tuple[FeatureRecord, ...]: ...


class FeatureManagementViewModel:
    def __init__(self, provider: FeatureManagementProvider) -> None:
        self._provider = provider

    def list_records(self) -> tuple[FeatureRecord, ...]:
        return self._provider.list_records()


class RegistryFeatureManagementProvider:
    def __init__(self, repository: object) -> None:
        self._repository = repository

    def list_records(self) -> tuple[FeatureRecord, ...]:
        return self._repository.list_all()


class AuthorizedRegistryFeatureManagementProvider:
    """Enforces registry-view permission at the application-facing provider boundary."""

    def __init__(self, repository: object, authorization: object, actor_id: str) -> None:
        self._repository = repository
        self._authorization = authorization
        self._actor_id = actor_id

    def list_records(self) -> tuple[FeatureRecord, ...]:
        self._authorization.require(self._actor_id, "feature.registry.view")
        return self._repository.list_all()
