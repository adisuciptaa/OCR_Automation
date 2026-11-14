"""Validated feature lifecycle transition policy."""
from app.core.exceptions import ApplicationError
from app.feature_manager.models import FeatureState

_ALLOWED = {
    FeatureState.DISCOVERED: {FeatureState.VALIDATING, FeatureState.QUARANTINED, FeatureState.ERROR},
    FeatureState.VALIDATING: {FeatureState.REGISTERED, FeatureState.QUARANTINED, FeatureState.ERROR},
    FeatureState.REGISTERED: {FeatureState.ENABLED, FeatureState.UNINSTALL_PENDING, FeatureState.ERROR},
    FeatureState.ENABLED: {FeatureState.DISABLED, FeatureState.UPDATE_PENDING, FeatureState.ERROR},
    FeatureState.DISABLED: {FeatureState.ENABLED, FeatureState.UPDATE_PENDING, FeatureState.UNINSTALL_PENDING, FeatureState.ERROR},
    FeatureState.UPDATE_PENDING: {FeatureState.ENABLED, FeatureState.DISABLED, FeatureState.ERROR},
    FeatureState.UNINSTALL_PENDING: {FeatureState.UNINSTALLED, FeatureState.DISABLED, FeatureState.ERROR},
    FeatureState.ERROR: {FeatureState.DISABLED, FeatureState.QUARANTINED},
    FeatureState.QUARANTINED: set(), FeatureState.UNINSTALLED: set(),
}


class FeatureLifecycleManager:
    @staticmethod
    def transition(current: FeatureState, target: FeatureState) -> FeatureState:
        if target not in _ALLOWED[current]:
            raise ApplicationError("FEATURE_LIFECYCLE_INVALID", f"Transition {current.value} → {target.value} is not allowed.")
        return target
