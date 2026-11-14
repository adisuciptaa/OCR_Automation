"""Process-local sessions with idle and absolute expiration."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from threading import RLock

from app.security.models import UserIdentity, UserSession


class SessionManager:
    def __init__(self, *, idle_timeout: timedelta = timedelta(minutes=30),
                 absolute_timeout: timedelta = timedelta(hours=12)) -> None:
        self.idle_timeout = idle_timeout
        self.absolute_timeout = absolute_timeout
        self._sessions: dict[str, UserSession] = {}
        self._lock = RLock()

    def create(self, identity: UserIdentity) -> UserSession:
        now = datetime.now(UTC)
        session = UserSession(secrets.token_urlsafe(32), identity.user_id, identity.username,
                              identity.display_name, now, now, now + self.absolute_timeout)
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> UserSession | None:
        now = datetime.now(UTC)
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if now >= session.expires_at or now - session.last_activity_at >= self.idle_timeout:
                self._sessions.pop(session_id, None)
                return None
            refreshed = UserSession(session.session_id, session.user_id, session.username,
                session.display_name, session.created_at, now, session.expires_at)
            self._sessions[session_id] = refreshed
            return refreshed

    def revoke(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def has_active_user_session(self, user_id: str) -> bool:
        with self._lock:
            session_ids = tuple(key for key, value in self._sessions.items() if value.user_id == user_id)
        return any(self.get(session_id) is not None for session_id in session_ids)

    def revoke_user(self, user_id: str) -> None:
        with self._lock:
            for key, session in tuple(self._sessions.items()):
                if session.user_id == user_id:
                    self._sessions.pop(key, None)
