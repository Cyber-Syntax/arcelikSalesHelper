"""Single explicit Decimal context for all domain arithmetic.

Using an explicit Context (instead of mutating the thread-global one) keeps the
precision independent of whatever the host application does.  No rounding is
applied to business values; 60 digits keeps divisions effectively exact.
"""

from __future__ import annotations

from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
)

CTX = Context(
    prec=60,
    rounding=ROUND_HALF_EVEN,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)

ZERO = Decimal(0)


def add(a: Decimal, b: Decimal) -> Decimal:
    return CTX.add(a, b)


def sub(a: Decimal, b: Decimal) -> Decimal:
    return CTX.subtract(a, b)


def mul(a: Decimal, b: Decimal) -> Decimal:
    return CTX.multiply(a, b)


def div(a: Decimal, b: Decimal) -> Decimal:
    return CTX.divide(a, b)


def mul_qty(a: Decimal, quantity: int) -> Decimal:
    return CTX.multiply(a, Decimal(quantity))
