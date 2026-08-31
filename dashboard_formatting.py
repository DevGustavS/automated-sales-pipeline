"""Format numeric dashboard values without changing their underlying types."""

from __future__ import annotations

import math
from collections.abc import Iterable

MISSING_VALUE = "—"


def _finite_number(value: object) -> float | None:
    """Return a finite float representation or ``None`` for invalid values."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None
    return 0.0 if number == 0 else number


def _pt_br_decimal(
    value: object,
    decimal_places: int,
    *,
    trim_trailing_zeros: bool = False,
) -> str:
    """Format a finite number with Brazilian decimal and thousands separators."""

    number = _finite_number(value)
    if number is None:
        return MISSING_VALUE

    formatted = f"{number:,.{decimal_places}f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    if trim_trailing_zeros and "," in formatted:
        formatted = formatted.rstrip("0").rstrip(",")
    return formatted


def brl(value: object) -> str:
    """Format a complete monetary value in Brazilian reais."""

    formatted = _pt_br_decimal(value, 2)
    return MISSING_VALUE if formatted == MISSING_VALUE else f"R$ {formatted}"


def compact_number(value: object, decimal_places: int = 1) -> str:
    """Format a quantity using ``mil``, ``M`` or ``B`` when appropriate."""

    number = _finite_number(value)
    if number is None:
        return MISSING_VALUE

    absolute = abs(number)
    if absolute >= 1_000_000_000:
        scaled, suffix = number / 1_000_000_000, "B"
    elif absolute >= 1_000_000:
        scaled, suffix = number / 1_000_000, "M"
    elif absolute >= 1_000:
        scaled, suffix = number / 1_000, "mil"
    else:
        places = 0 if number.is_integer() else decimal_places
        return _pt_br_decimal(number, places, trim_trailing_zeros=True)

    return f"{_pt_br_decimal(scaled, decimal_places)} {suffix}"


def compact_brl(value: object, decimal_places: int = 1) -> str:
    """Format money compactly while keeping values below one thousand complete."""

    number = _finite_number(value)
    if number is None:
        return MISSING_VALUE
    if abs(number) < 1_000:
        return brl(number)
    return f"R$ {compact_number(number, decimal_places)}"


def integer(value: object) -> str:
    """Format an integer with Brazilian thousands separators."""

    number = _finite_number(value)
    if number is None:
        return MISSING_VALUE
    return f"{int(number):,}".replace(",", ".")


def format_percentage(value: object, decimal_places: int = 2) -> str:
    """Format an already percentage-scaled value without changing its scale."""

    formatted = _pt_br_decimal(value, decimal_places)
    return MISSING_VALUE if formatted == MISSING_VALUE else f"{formatted}%"


def percentage(numerator: object, denominator: object) -> str:
    """Format a ratio as a percentage and handle a missing or zero denominator."""

    numerator_number = _finite_number(numerator)
    denominator_number = _finite_number(denominator)
    if numerator_number is None or denominator_number in (None, 0):
        return "0,00%"
    return format_percentage(numerator_number / denominator_number * 100)


def axis_ticks(values: Iterable[object], tick_count: int = 5) -> list[float]:
    """Build a small dynamic set of readable ticks around the supplied values."""

    finite_values = [
        number for value in values if (number := _finite_number(value)) is not None
    ]
    if not finite_values:
        return [0.0]

    lower = min(0.0, min(finite_values))
    upper = max(0.0, max(finite_values))
    if lower == upper:
        return [lower]

    raw_step = (upper - lower) / max(tick_count - 1, 1)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    normalized_step = raw_step / magnitude
    multiplier = next(
        candidate
        for candidate in (1.0, 2.0, 2.5, 5.0, 10.0)
        if normalized_step <= candidate
    )
    step = multiplier * magnitude
    start = math.floor(lower / step) * step
    end = math.ceil(upper / step) * step
    steps = round((end - start) / step)
    return [start + index * step for index in range(steps + 1)]
