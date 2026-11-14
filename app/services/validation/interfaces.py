"""Generic format and consistency validation interface."""
from typing import Protocol
from app.services.validation.models import ValidationResult

class ValidationService(Protocol):
    def validate_required_fields(self, values: object, required_fields: tuple[str, ...]) -> ValidationResult: ...
    def validate_identifier(self, value: str, *, pattern: str, field: str) -> ValidationResult: ...
