"""Service registration and read-only provider access."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any
from typing import Protocol, runtime_checkable

from app.core.exceptions import DuplicateServiceError, ServiceUnavailableError


@runtime_checkable
class ServiceProvider(Protocol):
    def get(self, service_id: str, version: str | None = None) -> object: ...


@dataclass(frozen=True, slots=True)
class _ServiceEntry:
    version: str
    instance: object


class ServiceProviderView:
    """Read-only service-provider facade exposed to application consumers."""

    def __init__(self, entries: dict[str, _ServiceEntry], lock: Any) -> None:
        self._entries = entries
        self._lock = lock

    def get(self, service_id: str, version: str | None = None) -> object:
        with self._lock:
            entry = self._entries.get(service_id)
            if entry is None:
                raise ServiceUnavailableError(
                    "SERVICE_UNAVAILABLE",
                    f"Required service '{service_id}' is not registered.",
                    details={"service_id": service_id},
                )
            if version is not None and not _service_version_matches(entry.version, version):
                raise ServiceUnavailableError(
                    "SERVICE_VERSION_INCOMPATIBLE",
                    f"Service '{service_id}' does not provide the requested version.",
                    details={
                        "service_id": service_id,
                        "requested_version": version,
                        "registered_version": entry.version,
                    },
                )
            return entry.instance


class ServiceRegistry:
    """Composition-root registry; feature consumers receive only provider view."""

    def __init__(self) -> None:
        self._entries: dict[str, _ServiceEntry] = {}
        self._lock = RLock()
        self._provider = ServiceProviderView(self._entries, self._lock)

    @property
    def provider(self) -> ServiceProvider:
        return self._provider

    def register(self, service_id: str, instance: object, *, version: str) -> None:
        if not service_id.strip() or not version.strip():
            raise ValueError("service_id and version must not be blank")
        with self._lock:
            if service_id in self._entries:
                raise DuplicateServiceError(
                    "SERVICE_ALREADY_REGISTERED",
                    f"Service '{service_id}' is already registered.",
                    details={"service_id": service_id},
                )
            self._entries[service_id] = _ServiceEntry(version=version, instance=instance)

    def contains(self, service_id: str) -> bool:
        with self._lock:
            return service_id in self._entries


def _service_version_matches(actual: str, requested: str) -> bool:
    """Match exact versions and the documented MAJOR.x / MAJOR.MINOR.x forms."""
    if requested == actual:
        return True
    actual_parts = actual.split(".")
    requested_parts = requested.split(".")
    if len(requested_parts) == 2 and requested_parts[1] == "x":
        return len(actual_parts) >= 1 and actual_parts[0] == requested_parts[0]
    if len(requested_parts) == 3 and requested_parts[2] == "x":
        return len(actual_parts) >= 2 and actual_parts[:2] == requested_parts[:2]
    return False
