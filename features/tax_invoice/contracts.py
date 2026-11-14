"""Typed Tax Invoice feature contract layered on the application FeatureModule."""
from __future__ import annotations

from typing import Mapping, Protocol

from app.core.job_contracts import JobRequest, JobResult
from app.feature_manager.models import FeatureDescriptor
from app.feature_manager.runtime_contracts import FeatureContext, UIContext


class TaxInvoiceFeatureContract(Protocol):
    """Public typed contract implemented by the Tax Invoice feature entry point."""

    def initialize(self, context: FeatureContext) -> None: ...

    def get_descriptor(self) -> FeatureDescriptor: ...

    def create_workspace(self, context: UIContext) -> object: ...

    def validate_configuration(self, config: Mapping[str, object]) -> object: ...

    def execute(self, request: JobRequest) -> JobResult: ...

    def shutdown(self) -> None: ...
