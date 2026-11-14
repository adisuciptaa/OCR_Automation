import pytest

from app.core.exceptions import ApplicationError
from app.feature_manager.lifecycle_manager import FeatureLifecycleManager
from app.feature_manager.models import FeatureState


def test_valid_feature_lifecycle_transition():
    assert FeatureLifecycleManager.transition(FeatureState.REGISTERED, FeatureState.ENABLED) is FeatureState.ENABLED


def test_invalid_feature_lifecycle_transition_is_rejected():
    with pytest.raises(ApplicationError) as error:
        FeatureLifecycleManager.transition(FeatureState.ENABLED, FeatureState.UNINSTALLED)
    assert error.value.code == "FEATURE_LIFECYCLE_INVALID"
