from __future__ import annotations

import re
from enum import Enum

from .result import Err, Ok, Result

MAX_QUANTITY = 1_000_000
_DIGITS = re.compile(r"[0-9]+")
_TOO_LARGE = f"Quantity cannot exceed {MAX_QUANTITY:,}."


class StockSource(Enum):
    MANUAL = "manual"
    CSV = "csv"


def validate_quantity(quantity: int) -> str | None:
    """Return an error message, or None when the quantity is acceptable."""
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        return "Quantity must be a whole number."
    if quantity < 0:
        return "Quantity cannot be negative."
    if quantity > MAX_QUANTITY:
        return _TOO_LARGE
    return None


def parse_quantity(text: str) -> Result[int, str]:
    """Whole numbers only: no separators, no decimals, no sign."""
    s = text.strip()
    if not s:
        return Err("Enter a whole number.")
    if s.startswith("-"):
        return Err("Quantity cannot be negative.")
    if not _DIGITS.fullmatch(s):
        return Err("Use digits only (a whole number such as 12).")
    if len(s.lstrip("0") or "0") > 7:  # also keeps int() away from huge inputs
        return Err(_TOO_LARGE)
    value = int(s)
    problem = validate_quantity(value)
    return Err(problem) if problem else Ok(value)
