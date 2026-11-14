"""Safe defaults used until authentication and trust provisioning are configured."""
from app.core.exceptions import ApplicationError


class DenyAllAuthorizationService:
    """Fail-closed authorization adapter; replace via composition root after AuthZ exists."""
    def require(self, actor_id: str, permission: str, resource: object | None = None) -> None:
        raise ApplicationError("FEATURE_PERMISSION_DENIED", "No authorization provider is configured.")

    def is_allowed(self, actor_id: str, permission: str, resource: object | None = None) -> bool:
        return False
