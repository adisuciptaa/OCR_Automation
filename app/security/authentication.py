"""Authentication workflows, first-administrator provisioning, and user administration."""
from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime, timedelta

from app.core.exceptions import ApplicationError
from app.security.audit import SecurityAuditService
from app.security.contracts import AuthorizationService, UserRepository
from app.security.models import RoleSummary, UserIdentity, UserSummary
from app.security.password_hasher import PasswordHasher


class AuthenticationManager:
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION = timedelta(minutes=15)
    _USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")

    def __init__(self, repository: UserRepository, password_hasher: PasswordHasher | None = None,
                 authorization: AuthorizationService | None = None,
                 audit_service: SecurityAuditService | None = None) -> None:
        self.repository = repository
        self.authorization = authorization
        self.audit_service = audit_service or SecurityAuditService(repository)
        self.password_hasher = password_hasher or PasswordHasher()
        self._dummy_hash = self.password_hasher.hash("not-a-real-user-password")

    def setup_initial_administrator(self, username: str, display_name: str, password: str) -> UserIdentity:
        if self.repository.has_users():
            raise ApplicationError("AUTH_INITIAL_SETUP_COMPLETE", "Initial administrator setup has already been completed.")
        normalized = self._validate_identity_fields(username, display_name)
        password_hash = self.password_hasher.hash(password)
        try:
            identity = self.repository.create_initial_admin(normalized, display_name.strip(), password_hash)
        except ValueError as exc:
            raise ApplicationError("AUTH_INITIAL_SETUP_COMPLETE", "Initial administrator setup has already been completed.") from exc
        self.audit_service.record(actor_id=identity.user_id, action="initial_admin_created",
                              target_user_id=identity.user_id, outcome="success")
        return identity

    def authenticate(self, username: str, password: str) -> UserIdentity:
        normalized = username.strip().casefold()
        record = self.repository.get_auth_record(normalized) if normalized else None
        now = datetime.now(UTC)
        if record is None:
            self.password_hasher.verify(password, self._dummy_hash)
            self.audit_service.record(actor_id=None, action="login", target_user_id=None,
                                  outcome="denied", error_code="AUTH_INVALID_CREDENTIALS")
            raise ApplicationError("AUTH_INVALID_CREDENTIALS", "Username or password is incorrect.")

        locked_until = record.locked_until
        if locked_until is not None and locked_until > now:
            self.password_hasher.verify(password, record.password_hash)
            self.audit_service.record(actor_id=None, action="login", target_user_id=record.user_id,
                                  outcome="denied", error_code="AUTH_ACCOUNT_LOCKED")
            raise ApplicationError("AUTH_ACCOUNT_LOCKED", "Account is temporarily locked. Try again later.")

        valid_password = self.password_hasher.verify(password, record.password_hash)
        if not valid_password or not record.is_active:
            attempts = record.failed_login_attempts + 1
            new_lock = now + self.LOCKOUT_DURATION if attempts >= self.MAX_FAILED_ATTEMPTS else None
            self.repository.record_failed_login(record.user_id, locked_until=new_lock)
            code = "AUTH_ACCOUNT_LOCKED" if new_lock else "AUTH_INVALID_CREDENTIALS"
            self.audit_service.record(actor_id=None, action="login", target_user_id=record.user_id,
                                  outcome="denied", error_code=code)
            message = "Account is temporarily locked. Try again later." if new_lock else "Username or password is incorrect."
            raise ApplicationError(code, message)

        self.repository.reset_login_failures(record.user_id)
        identity = self.repository.get_identity(record.user_id)
        if identity is None or not identity.is_active:
            raise ApplicationError("AUTH_INVALID_CREDENTIALS", "Username or password is incorrect.")
        self.audit_service.record(actor_id=identity.user_id, action="login", target_user_id=identity.user_id,
                              outcome="success")
        return identity

    def create_user(self, actor_id: str, username: str, display_name: str,
                    password: str, role_ids: tuple[str, ...]) -> UserIdentity:
        self._require(actor_id, "user.manage")
        normalized = self._validate_identity_fields(username, display_name)
        if not role_ids:
            raise ApplicationError("AUTH_ROLE_REQUIRED", "At least one role must be assigned to a new user.")
        password_hash = self.password_hasher.hash(password)
        try:
            identity = self.repository.create_user(normalized, display_name.strip(), password_hash, role_ids)
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise ApplicationError("AUTH_USERNAME_EXISTS", "That username is already in use.") from exc
            raise ApplicationError("AUTH_ROLE_INVALID", "One or more selected roles are invalid.") from exc
        self.audit_service.record(actor_id=actor_id, action="user_created", target_user_id=identity.user_id,
                              outcome="success", details={"roles": list(role_ids)})
        return identity

    def get_user_role_ids(self, actor_id: str, user_id: str) -> tuple[str, ...]:
        self._require(actor_id, "user.manage")
        if self.repository.get_identity(user_id) is None:
            raise ApplicationError("AUTH_USER_NOT_FOUND", "User does not exist.")
        return self.repository.get_user_role_ids(user_id)

    def update_user_roles(self, actor_id: str, user_id: str, role_ids: tuple[str, ...]) -> None:
        self._require(actor_id, "user.manage")
        if not role_ids:
            raise ApplicationError("AUTH_ROLE_REQUIRED", "At least one role must remain assigned.")
        if self.repository.get_identity(user_id) is None:
            raise ApplicationError("AUTH_USER_NOT_FOUND", "User does not exist.")
        currently_admin = self.repository.has_global_admin_permission(user_id)
        remains_admin = self.repository.role_ids_have_global_permission(role_ids)
        if currently_admin and not remains_admin and self.repository.count_active_global_administrators() <= 1:
            raise ApplicationError("AUTH_LAST_ADMIN_REQUIRED", "At least one active Administrator must remain.")
        try:
            self.repository.update_user_roles(user_id, role_ids)
        except sqlite3.IntegrityError as exc:
            raise ApplicationError("AUTH_ROLE_INVALID", "One or more selected roles are invalid.") from exc
        self.audit_service.record(actor_id=actor_id, action="user_roles_updated", target_user_id=user_id,
                              outcome="success", details={"roles": list(role_ids)})

    def set_user_active(self, actor_id: str, user_id: str, is_active: bool) -> None:
        self._require(actor_id, "user.manage")
        if self.repository.get_identity(user_id) is None:
            raise ApplicationError("AUTH_USER_NOT_FOUND", "User does not exist.")
        if actor_id == user_id and not is_active:
            raise ApplicationError("AUTH_SELF_DEACTIVATION_DENIED", "You cannot deactivate your own account.")
        if not is_active and self.repository.has_global_admin_permission(user_id) and self.repository.count_active_global_administrators() <= 1:
            raise ApplicationError("AUTH_LAST_ADMIN_REQUIRED", "At least one active Administrator must remain.")
        self.repository.set_user_active(user_id, is_active)
        self.audit_service.record(actor_id=actor_id, action="user_activated" if is_active else "user_deactivated",
                              target_user_id=user_id, outcome="success")

    def list_users(self, actor_id: str) -> tuple[UserSummary, ...]:
        self._require(actor_id, "user.manage")
        return self.repository.list_users()

    def list_roles(self, actor_id: str) -> tuple[RoleSummary, ...]:
        self._require(actor_id, "user.manage")
        return self.repository.list_roles()

    def _require(self, actor_id: str, permission: str) -> None:
        if self.authorization is None:
            raise ApplicationError("AUTH_PERMISSION_DENIED", "No authorization provider is configured.")
        self.authorization.require(actor_id, permission)

    @classmethod
    def _validate_identity_fields(cls, username: str, display_name: str) -> str:
        normalized = username.strip().casefold()
        if not cls._USERNAME_PATTERN.fullmatch(normalized):
            raise ApplicationError("AUTH_USERNAME_INVALID", "Username must be 3–32 characters using letters, numbers, dot, underscore, or hyphen.")
        if not display_name.strip() or len(display_name.strip()) > 80:
            raise ApplicationError("AUTH_DISPLAY_NAME_INVALID", "Display name must contain 1–80 characters.")
        return normalized
