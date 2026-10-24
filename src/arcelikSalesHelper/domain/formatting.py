from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .arith import CTX

_CENT = Decimal("0.01")


def format_money_input(amount: Decimal) -> str:
    """Turkish-style text for *editable* fields: 5.000,00.

    Unlike format_try it never rounds: every significant decimal is kept (minimum 2),
    so pre-filling a field from a stored product can never change its value.
    """
    if not amount.is_finite():
        raise ValueError("cannot format a non-finite amount")
    whole, _, frac = format(amount, "f").partition(".")
    sign = "-" if whole.startswith("-") else ""
    grouped = f"{int(whole.lstrip('-')):,}".replace(",", ".")
    return f"{sign}{grouped},{frac.rstrip('0').ljust(2, '0')}"


def format_try(amount: Decimal) -> str:
    """Turkish display format: 153.345,56 TL.  The only place values are rounded."""
    if not amount.is_finite():
        raise ValueError("cannot format a non-finite amount")
    q = amount.quantize(_CENT, rounding=ROUND_HALF_UP, context=CTX)
    negative = (
        q < 0
    )  # "-0.00" compares equal to zero, so no sign is shown for it
    whole, frac = format(q.copy_abs(), "f").split(".")
    grouped = f"{int(whole):,}".replace(",", ".")
    return f"{'-' if negative else ''}{grouped},{frac} TL"


def format_decimal_exact(amount: Decimal) -> str:
    """Canonical plain-decimal string (no exponent, '.' mark).  Also the storage form."""
    return format(amount, "f")
