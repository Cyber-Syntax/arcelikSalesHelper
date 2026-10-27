from __future__ import annotations

from decimal import Decimal


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
    """Format TRY without changing the Decimal value.

    Trailing zeroes beyond kuruş precision are omitted, but significant
    fractional digits are retained even when a value needs more than two.
    """
    if not amount.is_finite():
        raise ValueError("cannot format a non-finite amount")
    exact = format(amount.copy_abs(), "f")
    whole, dot, frac = exact.partition(".")
    if not dot:
        frac = "00"
    else:
        frac = frac.rstrip("0").ljust(2, "0")
    grouped = f"{int(whole):,}".replace(",", ".")
    negative = amount.is_signed() and amount != 0
    return f"{'-' if negative else ''}{grouped},{frac} TL"


def format_decimal_exact(amount: Decimal) -> str:
    """Canonical plain-decimal string (no exponent, '.' mark).  Also the storage form."""
    return format(amount, "f")
