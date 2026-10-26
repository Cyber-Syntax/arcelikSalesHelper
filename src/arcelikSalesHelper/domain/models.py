from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from arcelikSalesHelper import strings as T

POS_LABEL = T.POS_LABEL


class ConfirmationState(Enum):
    POS_UNVERIFIED = "pos_unverified"


class ManagerMode(Enum):
    UNIT = "unit"
    LINE = "line"


@dataclass(frozen=True)
class LineInput:
    product_name: str
    quantity: int
    regular_price: Decimal
    website_discounted_price: Decimal
    gift_selected: bool = False
    gift_name: str | None = None
    manager_value: Decimal | None = None
    manager_mode: ManagerMode | None = None
    product_id: int | None = None


@dataclass(frozen=True)
class LineWarning:
    code: str
    message: str
    line_index: int


@dataclass(frozen=True)
class LineResult:
    quantity: int
    regular_total: Decimal
    website_discounted_total: Decimal
    discount_amount: Decimal
    ten_pct_base: Decimal
    ten_pct_discount_unit: Decimal
    ten_pct_unit: Decimal
    ten_pct_total: Decimal
    manager_mode: ManagerMode | None
    manager_unit: Decimal | None
    manager_line_total: Decimal | None
    pos_amount: Decimal | None
    warnings: tuple[LineWarning, ...]


@dataclass(frozen=True)
class TotalValue:
    value: Decimal | None
    missing_lines: tuple[int, ...] = ()


@dataclass(frozen=True)
class TransactionTotals:
    regular: TotalValue
    website_discounted: TotalValue
    discount_amount: TotalValue
    ten_pct: TotalValue
    manager: TotalValue
    pos: TotalValue


@dataclass(frozen=True)
class TransactionResult:
    lines: tuple[LineResult, ...]
    totals: TransactionTotals


@dataclass(frozen=True)
class WebsiteOption:
    website_discounted_total: Decimal
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
