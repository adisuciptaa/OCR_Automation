"""Immutable public models for authentication, sessions, and access control."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AuthUserRecord:
    user_id: str
    username: str
    password_hash: str
    is_active: bool
    failed_login_attempts: int
    locked_until: datetime | None


@dataclass(frozen=True, slots=True)
class UserIdentity:
    user_id: str
    username: str
    display_name: str
    is_active: bool
    roles: tuple[str, ...]
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UserSummary:
    user_id: str
    username: str
    display_name: str
    is_active: bool
    roles: tuple[str, ...]
    created_at: datetime
    last_login_at: datetime | None


@dataclass(frozen=True, slots=True)
class RoleSummary:
    role_id: str
    name: str
    description: str
    is_system: bool


@dataclass(frozen=True, slots=True)
class UserSession:
    session_id: str
    user_id: str
    username: str
    display_name: str
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
