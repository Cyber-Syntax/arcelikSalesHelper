from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from functools import reduce

from arcelikSalesHelper import strings as T

from .arith import ZERO, add, div, mul, mul_qty, sub
from .models import GiftOption, LineInput, LineResult, ManagerMode, TotalValue, TransactionResult, TransactionTotals, WebsiteOption
from .result import Err, Ok, Result
from .validation import ValidationError, soft_warnings, validate_line

TEN_PERCENT = Decimal("0.10")


def ten_percent(base: Decimal) -> tuple[Decimal, Decimal]:
    discount = mul(base, TEN_PERCENT)
    return discount, sub(base, discount)


def discount_base(line: LineInput) -> Decimal:
    return line.regular_price if line.gift_selected else line.website_discounted_price


def manager_totals(value: Decimal, mode: ManagerMode, quantity: int) -> tuple[Decimal, Decimal]:
    """Return unit display value and authoritative line total."""
    if mode is ManagerMode.UNIT:
        return value, mul_qty(value, quantity)
    return div(value, Decimal(quantity)), value


def pos_amount(regular_total: Decimal, website_discounted_total: Decimal, manager_line_total: Decimal) -> Decimal:
    return add(sub(regular_total, website_discounted_total), manager_line_total)


def _compute_line(line: LineInput, line_index: int) -> LineResult:
    qty = line.quantity
    regular_total = mul_qty(line.regular_price, qty)
    website_total = mul_qty(line.website_discounted_price, qty)
    base = discount_base(line)
    discount, ten_unit = ten_percent(base)
    unit: Decimal | None = None
    total: Decimal | None = None
    pos: Decimal | None = None
    if line.manager_value is not None and line.manager_mode is not None:
        unit, total = manager_totals(line.manager_value, line.manager_mode, qty)
        pos = pos_amount(regular_total, website_total, total)
    return LineResult(
        quantity=qty, regular_total=regular_total,
        website_discounted_total=website_total,
        discount_amount=sub(regular_total, website_total),
        ten_pct_base=base, ten_pct_discount_unit=discount,
        ten_pct_unit=ten_unit, ten_pct_total=mul_qty(ten_unit, qty),
        manager_mode=line.manager_mode if total is not None else None,
        manager_unit=unit, manager_line_total=total, pos_amount=pos,
        warnings=soft_warnings(line_index, total, website_total),
    )


def calculate_line(line: LineInput, line_index: int = 0) -> Result[LineResult, tuple[ValidationError, ...]]:
    errors = validate_line(line, line_index)
    return Err(errors) if errors else Ok(_compute_line(line, line_index))


def _total(values: Sequence[Decimal | None]) -> TotalValue:
    missing = tuple(i for i, value in enumerate(values) if value is None)
    if missing:
        return TotalValue(None, missing)
    return TotalValue(reduce(add, (v for v in values if v is not None), ZERO))


def _totals(results: Sequence[LineResult]) -> TransactionTotals:
    return TransactionTotals(
        regular=_total([r.regular_total for r in results]),
        website_discounted=_total([r.website_discounted_total for r in results]),
        discount_amount=_total([r.discount_amount for r in results]),
        ten_pct=_total([r.ten_pct_total for r in results]),
        manager=_total([r.manager_line_total for r in results]),
        pos=_total([r.pos_amount for r in results]),
    )


def calculate_transaction(lines: Sequence[LineInput]) -> Result[TransactionResult, tuple[ValidationError, ...]]:
    if not lines:
        return Err((ValidationError("no_lines", "lines", T.VAL_NO_LINES),))
    errors = tuple(e for i, line in enumerate(lines) for e in validate_line(line, i))
    if errors:
        return Err(errors)
    results = tuple(_compute_line(line, i) for i, line in enumerate(lines))
    return Ok(TransactionResult(results, _totals(results)))


def build_options(line: LineInput, result: LineResult) -> tuple[WebsiteOption, GiftOption | None]:
    qty = result.quantity
    site_discount, site_unit = ten_percent(line.website_discounted_price)
    manager = (result.manager_mode, result.manager_unit, result.manager_line_total)
    empty = (None, None, None)
    website = WebsiteOption(
        website_discounted_total=result.website_discounted_total,
        ten_pct_base=line.website_discounted_price,
        ten_pct_discount_unit=site_discount, ten_pct_unit=site_unit,
        ten_pct_total=mul_qty(site_unit, qty),
        manager_mode=(empty if line.gift_selected else manager)[0],
        manager_unit=(empty if line.gift_selected else manager)[1],
        manager_line_total=(empty if line.gift_selected else manager)[2],
    )
    name = (line.gift_name or "").strip()
    if not (line.gift_selected or name):
        return website, None
    gift_discount, gift_unit = ten_percent(line.regular_price)
    gift_manager = manager if line.gift_selected else empty
    gift = GiftOption(
        gift_name=name or None, regular_total=result.regular_total,
        ten_pct_base=line.regular_price, ten_pct_discount_unit=gift_discount,
        ten_pct_unit=gift_unit, ten_pct_total=mul_qty(gift_unit, qty),
        manager_mode=gift_manager[0], manager_unit=gift_manager[1],
        manager_line_total=gift_manager[2],
    )
    return website, gift
