"""Application-facing security audit writer; persistence remains repository-owned."""
from __future__ import annotations

from collections.abc import Mapping

from app.security.contracts import UserRepository


class SecurityAuditService:
    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    def record(self, *, actor_id: str | None, action: str, target_user_id: str | None,
               outcome: str, error_code: str | None = None,
               details: Mapping[str, object] | None = None) -> None:
        self._repository.audit(
            actor_id=actor_id,
            action=action,
            target_user_id=target_user_id,
            outcome=outcome,
            error_code=error_code,
            details=dict(details or {}),
        )
