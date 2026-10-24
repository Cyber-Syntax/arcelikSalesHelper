from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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
            "Quantity must be a whole number of at least 1.",
        )

    if _bad_money(line.regular_price):
        err(
            "regular_price_invalid",
            "regular_price",
            "Regular price must be zero or more.",
        )
    website_ok = not _bad_money(line.website_price)
    if not website_ok:
        err(
            "website_price_invalid",
            "website_price",
            "Website price must be zero or more.",
        )

    if _bad_money(line.coupon):
        err("coupon_negative", "coupon", "Coupon amount must be zero or more.")
    elif website_ok and line.coupon > line.website_price:
        err(
            "coupon_exceeds_website",
            "coupon",
            "Coupon amount cannot exceed the website discounted price.",
        )

    if line.manager_value is not None:
        if _bad_money(line.manager_value):
            err(
                "manager_value_invalid",
                "manager_value",
                "Manager value must be zero or more.",
            )
        if line.manager_mode is None:
            err(
                "manager_mode_required",
                "manager_mode",
                "Choose unit price or total line price.",
            )
    elif line.manager_mode is not None:
        err(
            "manager_mode_without_value",
            "manager_mode",
            "Manager mode was given without a manager value.",
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
                message=(
                    "Manager line total is higher than the applicable website total. "
                    "The value is used exactly as entered."
                ),
                line_index=line_index,
            ),
        )
    return ()
