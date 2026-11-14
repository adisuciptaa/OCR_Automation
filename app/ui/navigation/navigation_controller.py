"""Validates presentation navigation targets against the current feature catalog."""

from __future__ import annotations

from app.ui.view_models.feature_catalog import FeatureSummary


class NavigationController:
    """Small presentation-layer guard; it is not an authorization service."""

    STATIC_PAGES = frozenset({"dashboard", "feature_cms", "settings", "users"})

    def __init__(self) -> None:
        self._feature_ids: frozenset[str] = frozenset()

    def set_available_features(self, features: tuple[FeatureSummary, ...]) -> None:
        self._feature_ids = frozenset(feature.feature_id for feature in features)

    def can_navigate_to_page(self, page_key: str) -> bool:
        return page_key in self.STATIC_PAGES

    def can_open_feature(self, feature_id: str) -> bool:
        return feature_id in self._feature_ids
