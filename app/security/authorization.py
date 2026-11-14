"""Permission-based authorization implementation for application boundaries."""
from __future__ import annotations

from app.core.exceptions import ApplicationError
from app.security.audit import SecurityAuditService
from app.security.contracts import SessionService, UserRepository


class RbacAuthorizationService:
    def __init__(self, repository: UserRepository, session_manager: SessionService | None = None,
                 audit_service: SecurityAuditService | None = None) -> None:
        self.repository = repository
        self.session_manager = session_manager
        self.audit_service = audit_service or SecurityAuditService(repository)

    def is_allowed(self, actor_id: str, permission: str, resource: object | None = None) -> bool:
        if not actor_id or not permission:
            return False
        if self.session_manager is not None and not self.session_manager.has_active_user_session(actor_id):
            return False
        return bool(self.repository.user_has_permission(actor_id, permission))

    def require(self, actor_id: str, permission: str, resource: object | None = None) -> None:
        if not self.is_allowed(actor_id, permission, resource):
            try:
                self.audit_service.record(actor_id=actor_id or None, action="authorization_denied",
                    target_user_id=actor_id or None, outcome="denied", error_code="AUTH_PERMISSION_DENIED",
                    details={"permission": permission})
            except Exception:
                # Authorization must remain fail-closed even if audit persistence is unavailable.
                pass
            raise ApplicationError("AUTH_PERMISSION_DENIED", "You are not authorized to perform this action.")
