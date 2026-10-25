from __future__ import annotations

import re
from enum import Enum

from arcelikSalesHelper import strings as T

from .result import Err, Ok, Result

MAX_QUANTITY = 1_000_000
_DIGITS = re.compile(r"[0-9]+")
_TOO_LARGE = T.stock_too_large(MAX_QUANTITY)


class StockSource(Enum):
    MANUAL = "manual"
    CSV = "csv"


def validate_quantity(quantity: int) -> str | None:
    """Return an error message, or None when the quantity is acceptable."""
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        return T.STOCK_NOT_WHOLE
    if quantity < 0:
        return T.STOCK_NEGATIVE
    if quantity > MAX_QUANTITY:
        return _TOO_LARGE
    return None


def parse_quantity(text: str) -> Result[int, str]:
    """Whole numbers only: no separators, no decimals, no sign."""
    s = text.strip()
    if not s:
        return Err(T.STOCK_ENTER_WHOLE)
    if s.startswith("-"):
        return Err(T.STOCK_NEGATIVE)
    if not _DIGITS.fullmatch(s):
        return Err(T.STOCK_DIGITS_ONLY)
    if len(s.lstrip("0") or "0") > 7:  # also keeps int() away from huge inputs
        return Err(_TOO_LARGE)
    value = int(s)
    problem = validate_quantity(value)
    return Err(problem) if problem else Ok(value)
