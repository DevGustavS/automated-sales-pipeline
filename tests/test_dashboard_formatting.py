from __future__ import annotations

import math

import pytest

from dashboard_formatting import (
    axis_ticks,
    brl,
    compact_brl,
    compact_number,
    format_percentage,
    percentage,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (32_547_527_600, "R$ 32,5 B"),
        (751_462_600, "R$ 751,5 M"),
        (282_724.50, "R$ 282,7 mil"),
        (850, "R$ 850,00"),
        (-1_250_000, "R$ -1,2 M"),
    ],
)
def test_compact_brl_uses_dashboard_scale(value: float, expected: str) -> None:
    assert compact_brl(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (115_121, "115,1 mil"),
        (1_500_000, "1,5 M"),
        (2_500_000_000, "2,5 B"),
        (942, "942"),
        (-1_500, "-1,5 mil"),
    ],
)
def test_compact_number_formats_quantities(value: float, expected: str) -> None:
    assert compact_number(value) == expected


def test_complete_brl_and_percentage_use_brazilian_separators() -> None:
    assert brl(1_280_000) == "R$ 1.280.000,00"
    assert format_percentage(1.54) == "1,54%"
    assert percentage(5, 6) == "83,33%"
    assert percentage(0, 0) == "0,00%"


@pytest.mark.parametrize("value", [None, math.nan, math.inf, -math.inf])
def test_formatters_do_not_render_non_finite_values(value: float | None) -> None:
    assert brl(value) == "—"
    assert compact_brl(value) == "—"
    assert compact_number(value) == "—"
    assert format_percentage(value) == "—"


def test_axis_ticks_are_dynamic_and_limited() -> None:
    ticks = axis_ticks([250_000, 1_252_000])

    assert ticks[0] == 0
    assert ticks[-1] >= 1_252_000
    assert len(ticks) <= 6
