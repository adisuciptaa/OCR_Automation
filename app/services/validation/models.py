"""Generic validation result models."""
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"
    field: str | None = None

@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    issues: tuple[ValidationIssue, ...] = ()
