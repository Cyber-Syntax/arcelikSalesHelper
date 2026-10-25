from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arcelikSalesHelper import strings as T

from .models import LineInput, LineWarning


@dataclass(frozen=True)
class ValidationError:
    code: str
    field: str
    message: str
    line_index: int | None = None  # 0-based; None for transaction-level errors


def _bad_money(d: Decimal) -> bool:
    return (not d.is_finite()) or d < 0


def validate_line(
    line: LineInput, line_index: int = 0
) -> tuple[ValidationError, ...]:
    errors: list[ValidationError] = []

    def err(code: str, field: str, message: str) -> None:
        errors.append(ValidationError(code, field, message, line_index))

    q = line.quantity
    if isinstance(q, bool) or not isinstance(q, int) or q < 1:
        err(
            "quantity_invalid",
            "quantity",
            T.VAL_QUANTITY,
        )

    if _bad_money(line.regular_price):
        err(
            "regular_price_invalid",
            "regular_price",
            T.VAL_REGULAR_PRICE,
        )
    website_ok = not _bad_money(line.website_price)
    if not website_ok:
        err(
            "website_price_invalid",
            "website_price",
            T.VAL_WEBSITE_PRICE,
        )

    if _bad_money(line.coupon):
        err("coupon_negative", "coupon", T.VAL_COUPON_NEGATIVE)
    elif website_ok and line.coupon > line.website_price:
        err(
            "coupon_exceeds_website",
            "coupon",
            T.VAL_COUPON_EXCEEDS,
        )

    if line.manager_value is not None:
        if _bad_money(line.manager_value):
            err(
                "manager_value_invalid",
                "manager_value",
                T.VAL_MANAGER_VALUE,
            )
        if line.manager_mode is None:
            err(
                "manager_mode_required",
                "manager_mode",
                T.VAL_MANAGER_MODE_REQUIRED,
            )
    elif line.manager_mode is not None:
        err(
            "manager_mode_without_value",
            "manager_mode",
            T.VAL_MANAGER_MODE_WITHOUT_VALUE,
        )

    return tuple(errors)


def soft_warnings(
    line_index: int,
    gift_selected: bool,
    manager_line_total: Decimal | None,
    website_total: Decimal,
    effective_website_total: Decimal,
) -> tuple[LineWarning, ...]:
    """Non-blocking warnings.  The manager value is never altered."""
    if manager_line_total is None:
        return ()
    applicable = website_total if gift_selected else effective_website_total
    if manager_line_total > applicable:
        return (
            LineWarning(
                code="manager_exceeds_website",
                message=T.WARN_MANAGER_EXCEEDS,
                line_index=line_index,
            ),
        )
    return ()
