from __future__ import annotations

from datetime import UTC, datetime

from app.feature_manager.models import ConfigurationScope, FeatureConfiguration
from app.persistence.repositories.feature_configuration_repository import SQLiteFeatureConfigurationRepository


def test_configuration_repository_round_trip_and_scope_isolation(tmp_path):
    repository = SQLiteFeatureConfigurationRepository(tmp_path / "config.sqlite3")
    now = datetime.now(UTC)
    configuration = FeatureConfiguration("invoice_reader", ConfigurationScope.USER, "user-1", 3,
        {"language": "id", "dpi": 300}, now, now, "admin")
    repository.save(configuration)
    assert repository.get("invoice_reader", ConfigurationScope.USER, "user-1") == configuration
    assert repository.get("invoice_reader", ConfigurationScope.USER, "user-2") is None
    assert repository.list_for_feature("invoice_reader") == (configuration,)
    repository.delete("invoice_reader", ConfigurationScope.USER, "user-1")
    assert repository.list_for_feature("invoice_reader") == ()
