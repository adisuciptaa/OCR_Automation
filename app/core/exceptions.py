"""Structured application exceptions and stable error codes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ApplicationError(Exception):
    """Base exception carrying a stable code and a safe user-facing message."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.details = dict(details or {})


class ConfigurationError(ApplicationError):
    """Raised when application configuration cannot be loaded or saved."""


class LifecycleError(ApplicationError):
    """Raised when an application lifecycle transition is invalid."""


class ServiceUnavailableError(ApplicationError):
    """Raised when a requested service is not registered or compatible."""


class DuplicateServiceError(ApplicationError):
    """Raised when a service ID is registered more than once."""
