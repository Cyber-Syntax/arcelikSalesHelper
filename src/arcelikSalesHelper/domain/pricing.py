from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from functools import reduce

from .arith import ZERO, add, div, mul, mul_qty, sub
from .models import (
    GiftOption,
    LineInput,
    LineResult,
    ManagerMode,
    TotalValue,
    TransactionResult,
    TransactionTotals,
    WebsiteOption,
)
from .result import Err, Ok, Result
from .validation import ValidationError, soft_warnings, validate_line

TEN_PERCENT = Decimal("0.10")


def effective_website_unit(website: Decimal, coupon: Decimal) -> Decimal:
    return sub(website, coupon)


def ten_percent(base: Decimal) -> tuple[Decimal, Decimal]:
    """Return (discount_amount, scenario_price) for a unit base."""
    discount = mul(base, TEN_PERCENT)
    return discount, sub(base, discount)


def discount_base(line: LineInput) -> Decimal:
    """Gift -> regular price; no gift -> effective website price."""
    if line.gift_selected:
        return line.regular_price
    return effective_website_unit(line.website_price, line.coupon)


def manager_totals(
    value: Decimal, mode: ManagerMode, quantity: int
) -> tuple[Decimal, Decimal]:
    """Return (unit, line_total).  In LINE mode the entered value IS the line total;
    the unit value is derived for display only and never feeds back into totals.
    """
    if mode is ManagerMode.UNIT:
        return value, mul_qty(value, quantity)
    return div(value, Decimal(quantity)), value


def pos_amount(
    regular_total: Decimal, website_total: Decimal, manager_line_total: Decimal
) -> Decimal:
    """(regular line total - NORMAL website line total) + manager line total.
    The coupon is deliberately not part of this formula.
    """
    return add(sub(regular_total, website_total), manager_line_total)


def _compute_line(line: LineInput, line_index: int) -> LineResult:
    """Precondition: ``validate_line`` returned no errors."""
    qty = line.quantity
    eff_unit = effective_website_unit(line.website_price, line.coupon)
    regular_total = mul_qty(line.regular_price, qty)
    website_total = mul_qty(line.website_price, qty)
    coupon_total = mul_qty(line.coupon, qty)
    eff_total = mul_qty(eff_unit, qty)

    discount_unit, ten_unit = ten_percent(discount_base(line))

    m_unit: Decimal | None = None
    m_line: Decimal | None = None
    pos: Decimal | None = None
    if line.manager_value is not None and line.manager_mode is not None:
        m_unit, m_line = manager_totals(
            line.manager_value, line.manager_mode, qty
        )
        pos = pos_amount(regular_total, website_total, m_line)

    return LineResult(
        quantity=qty,
        regular_total=regular_total,
        website_total=website_total,
        coupon_total=coupon_total,
        effective_website_unit=eff_unit,
        effective_website_total=eff_total,
        ten_pct_base=discount_base(line),
        ten_pct_discount_unit=discount_unit,
        ten_pct_unit=ten_unit,
        ten_pct_total=mul_qty(ten_unit, qty),
        manager_mode=line.manager_mode if m_line is not None else None,
        manager_unit=m_unit,
        manager_line_total=m_line,
        pos_amount=pos,
        warnings=soft_warnings(
            line_index, line.gift_selected, m_line, website_total, eff_total
        ),
    )


def calculate_line(
    line: LineInput, line_index: int = 0
) -> Result[LineResult, tuple[ValidationError, ...]]:
    errors = validate_line(line, line_index)
    if errors:
        return Err(errors)
    return Ok(_compute_line(line, line_index))


def _total(values: Sequence[Decimal | None]) -> TotalValue:
    missing = tuple(i for i, v in enumerate(values) if v is None)
    if missing:
        return TotalValue(None, missing)
    present = [v for v in values if v is not None]
    return TotalValue(reduce(add, present, ZERO))


def _totals(results: Sequence[LineResult]) -> TransactionTotals:
    return TransactionTotals(
        regular=_total([r.regular_total for r in results]),
        website=_total([r.website_total for r in results]),
        effective_website=_total([r.effective_website_total for r in results]),
        ten_pct=_total([r.ten_pct_total for r in results]),
        manager=_total([r.manager_line_total for r in results]),
        pos=_total([r.pos_amount for r in results]),
    )


def calculate_transaction(
    lines: Sequence[LineInput],
) -> Result[TransactionResult, tuple[ValidationError, ...]]:
    if not lines:
        return Err(
            (
                ValidationError(
                    "no_lines", "lines", "Add at least one product line."
                ),
            )
        )
    errors = tuple(
        e for i, ln in enumerate(lines) for e in validate_line(ln, i)
    )
    if errors:
        return Err(errors)
    results = tuple(_compute_line(ln, i) for i, ln in enumerate(lines))
    return Ok(TransactionResult(lines=results, totals=_totals(results)))


def build_options(
    line: LineInput, result: LineResult
) -> tuple[WebsiteOption, GiftOption | None]:
    """Present the two options side by side.  Never ranks or recommends.

    Each option shows its own 10% scenario (website: effective website price base;
    gift: regular price base).  The line's manager value is attached to the option
    matching the line's gift state, so it is never assigned to the other option.
    """
    qty = result.quantity
    site_disc, site_unit = ten_percent(result.effective_website_unit)
    mgr = (result.manager_mode, result.manager_unit, result.manager_line_total)
    no_mgr: tuple[ManagerMode | None, Decimal | None, Decimal | None] = (
        None,
        None,
        None,
    )

    website = WebsiteOption(
        website_total=result.website_total,
        coupon_total=result.coupon_total,
        effective_unit=result.effective_website_unit,
        effective_total=result.effective_website_total,
        ten_pct_base=result.effective_website_unit,
        ten_pct_discount_unit=site_disc,
        ten_pct_unit=site_unit,
        ten_pct_total=mul_qty(site_unit, qty),
        manager_mode=(no_mgr if line.gift_selected else mgr)[0],
        manager_unit=(no_mgr if line.gift_selected else mgr)[1],
        manager_line_total=(no_mgr if line.gift_selected else mgr)[2],
    )

    name = (line.gift_name or "").strip()
    if not (line.gift_selected or name):
        return website, None

    gift_disc, gift_unit = ten_percent(line.regular_price)
    g_mgr = mgr if line.gift_selected else no_mgr
    gift = GiftOption(
        gift_name=name or None,
        regular_total=result.regular_total,
        ten_pct_base=line.regular_price,
        ten_pct_discount_unit=gift_disc,
        ten_pct_unit=gift_unit,
        ten_pct_total=mul_qty(gift_unit, qty),
        manager_mode=g_mgr[0],
        manager_unit=g_mgr[1],
        manager_line_total=g_mgr[2],
    )
    return website, gift
