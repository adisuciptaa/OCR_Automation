from __future__ import annotations

import pytest

from app.core.exceptions import DuplicateServiceError, ServiceUnavailableError
from app.core.service_registry import ServiceRegistry


def test_service_registry_resolves_registered_service() -> None:
    registry = ServiceRegistry()
    service = object()
    registry.register("ocr.recognize", service, version="1.0")
    assert registry.provider.get("ocr.recognize", "1.0") is service


def test_service_registry_rejects_duplicate_registration() -> None:
    registry = ServiceRegistry()
    registry.register("pdf.render", object(), version="1.0")
    with pytest.raises(DuplicateServiceError):
        registry.register("pdf.render", object(), version="1.0")


def test_service_provider_rejects_missing_or_incompatible_service() -> None:
    registry = ServiceRegistry()
    with pytest.raises(ServiceUnavailableError):
        registry.provider.get("missing.service")
    registry.register("excel.workbook", object(), version="1.0")
    with pytest.raises(ServiceUnavailableError) as error:
        registry.provider.get("excel.workbook", "2.0")
    assert error.value.code == "SERVICE_VERSION_INCOMPATIBLE"


def test_provider_view_does_not_expose_registry_mutation() -> None:
    registry = ServiceRegistry()
    assert not hasattr(registry.provider, "register")


def test_service_provider_supports_major_version_wildcard() -> None:
    registry = ServiceRegistry()
    service = object()
    registry.register("pdf.render", service, version="1.4.2")
    assert registry.provider.get("pdf.render", "1.x") is service
    assert registry.provider.get("pdf.render", "1.4.x") is service
    with pytest.raises(ServiceUnavailableError):
        registry.provider.get("pdf.render", "2.x")
