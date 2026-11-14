"""Shared immutable value objects that do not expose vendor engine types."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NormalizedRegion:
    """A normalized rectangle with coordinates in the inclusive [0, 1] range."""
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if any(not 0.0 <= value <= 1.0 for value in values):
            raise ValueError("Region coordinates must be between 0 and 1.")
        if self.width <= 0 or self.height <= 0 or self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Region must have positive dimensions and remain inside the page.")


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Resource ceilings applied by concrete adapters."""
    max_file_bytes: int = 100 * 1024 * 1024
    max_pages: int = 500
    max_image_pixels: int = 40_000_000
    max_render_dpi: int = 400

    def __post_init__(self) -> None:
        if min(self.max_file_bytes, self.max_pages, self.max_image_pixels, self.max_render_dpi) <= 0:
            raise ValueError("All resource limits must be positive.")


@dataclass(frozen=True, slots=True)
class ServiceMetadata:
    service_id: str
    version: str
    implementation_id: str
