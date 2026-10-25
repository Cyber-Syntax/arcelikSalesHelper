from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

POS_LABEL = "POS-entry calculation (verify before use)"


class ConfirmationState(Enum):
    """What the UI told the user about the result when it was saved."""

    POS_UNVERIFIED = "pos_unverified"


class ManagerMode(Enum):
    UNIT = "unit"
    LINE = "line"


@dataclass(frozen=True)
class LineInput:
    product_name: str
    quantity: int
    regular_price: Decimal
    website_price: Decimal
    coupon: Decimal = Decimal(0)
    gift_selected: bool = False
    gift_name: str | None = None
    manager_value: Decimal | None = None
    manager_mode: ManagerMode | None = None
    product_id: int | None = None


@dataclass(frozen=True)
class LineWarning:
    code: str
    message: str
    line_index: int  # 0-based; the UI displays +1


@dataclass(frozen=True)
class LineResult:
    quantity: int
    regular_total: Decimal
    website_total: Decimal
    coupon_total: Decimal
    effective_website_unit: Decimal
    effective_website_total: Decimal
    ten_pct_base: Decimal
    ten_pct_discount_unit: Decimal
    ten_pct_unit: Decimal
    ten_pct_total: Decimal
    manager_mode: ManagerMode | None
    manager_unit: Decimal | None  # derived for display when mode is LINE
    manager_line_total: Decimal | None  # authoritative
    pos_amount: Decimal | None
    warnings: tuple[LineWarning, ...]


@dataclass(frozen=True)
class TotalValue:
    """A transaction total, or the reason it is unavailable.

    ``value`` is None when any line lacks the input; ``missing_lines`` then lists
    the 0-based indices so the UI can say "n/a: missing manager value on line N".
    """

    value: Decimal | None
    missing_lines: tuple[int, ...] = ()


@dataclass(frozen=True)
class TransactionTotals:
    regular: TotalValue
    website: TotalValue
    effective_website: TotalValue
    ten_pct: TotalValue
    manager: TotalValue
    pos: TotalValue


@dataclass(frozen=True)
class TransactionResult:
    lines: tuple[LineResult, ...]
    totals: TransactionTotals


@dataclass(frozen=True)
class WebsiteOption:
    website_total: Decimal
    coupon_total: Decimal
    effective_unit: Decimal
    effective_total: Decimal
    ten_pct_base: Decimal
    ten_pct_discount_unit: Decimal
    ten_pct_unit: Decimal
    ten_pct_total: Decimal
    manager_mode: ManagerMode | None
    manager_unit: Decimal | None
    manager_line_total: Decimal | None


@dataclass(frozen=True)
class GiftOption:
    gift_name: str | None
    regular_total: Decimal
    ten_pct_base: Decimal
    ten_pct_discount_unit: Decimal
    ten_pct_unit: Decimal
    ten_pct_total: Decimal
    manager_mode: ManagerMode | None
    manager_unit: Decimal | None
    manager_line_total: Decimal | None
