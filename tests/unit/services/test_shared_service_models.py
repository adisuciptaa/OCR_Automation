from __future__ import annotations

import pytest

from app.services.models import NormalizedRegion, ResourceLimits


def test_normalized_region_accepts_valid_region() -> None:
    assert NormalizedRegion(0.1, 0.2, 0.3, 0.4).width == 0.3


@pytest.mark.parametrize(
    "values",
    [(-0.1, 0.0, 0.2, 0.2), (0.9, 0.0, 0.2, 0.2), (0.0, 0.0, 0.0, 0.2)],
)
def test_normalized_region_rejects_invalid_region(values: tuple[float, ...]) -> None:
    with pytest.raises(ValueError):
        NormalizedRegion(*values)


def test_resource_limits_reject_non_positive_values() -> None:
    with pytest.raises(ValueError):
        ResourceLimits(max_pages=0)
