"""Domain-facing Feature Registry facade over the persistence repository."""
from __future__ import annotations

from app.feature_manager.contracts import FeatureRegistryRepository
from app.feature_manager.models import FeatureRecord


class FeatureRegistry:
    """Centralizes registry access without exposing SQLite to Feature Manager callers."""
    def __init__(self, repository: FeatureRegistryRepository) -> None:
        self._repository = repository

    def get(self, feature_id: str) -> FeatureRecord | None:
        return self._repository.get(feature_id)

    def list_all(self) -> tuple[FeatureRecord, ...]:
        return self._repository.list_all()

    def save(self, record: FeatureRecord) -> None:
        self._repository.save(record)

    def delete(self, feature_id: str) -> None:
        self._repository.delete(feature_id)

    def audit(self, **values: object) -> None:
        audit = getattr(self._repository, "audit", None)
        if callable(audit):
            audit(**values)
