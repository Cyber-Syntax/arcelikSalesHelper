"""Raw form text -> validated LineInput -> LineResult -> display model.

Pure: the UI only collects strings, calls ``evaluate_line`` and renders the
returned ``ResultView``.  All numbers shown come from ``LineResult``; nothing is
recomputed here (only formatted).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arcelikSalesHelper.domain.arith import ZERO
from arcelikSalesHelper.domain.formatting import (
    format_decimal_exact,
    format_try,
)
from arcelikSalesHelper.domain.models import (
    POS_LABEL,
    LineInput,
    LineResult,
    ManagerMode,
)
from arcelikSalesHelper.domain.money import parse_money_ex
from arcelikSalesHelper.domain.pricing import calculate_line
from arcelikSalesHelper.domain.result import Err, Ok

# ---- input ----------------------------------------------------------------


@dataclass(frozen=True)
class LineForm:
    """Exactly what the widgets contain, as raw text."""

    product_name: str
    quantity: int = 1
    regular_price: str = ""
    website_price: str = ""
    coupon: str = ""
    gift_selected: bool = False
    gift_name: str = ""
    manager_value: str = ""
    manager_mode: ManagerMode = ManagerMode.UNIT
    product_id: int | None = None


@dataclass(frozen=True)
class MoneyRead:
    value: Decimal | None
    error: str | None
    hint: str | None
    empty: bool


def read_money(text: str) -> MoneyRead:
    if not text.strip():
        return MoneyRead(None, "Enter an amount.", None, True)
    match parse_money_ex(text):
        case Ok(parsed):
            hint = (
                f"Read as {format_try(parsed.value)}. "
                "Use a comma for decimals (for example 1,234)."
                if parsed.ambiguous
                else None
            )
            return MoneyRead(parsed.value, None, hint, False)
        case Err(message):
            return MoneyRead(None, message, None, False)
    raise AssertionError("unreachable")  # pragma: no cover


# ---- output ---------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    label: str
    value: str
    tooltip: str | None = None


@dataclass(frozen=True)
class Section:
    title: str
    rows: tuple[Row, ...]
    note: str | None = None


@dataclass(frozen=True)
class ResultView:
    sections: tuple[Section, ...]
    warnings: tuple[str, ...]
    explanation: tuple[str, ...]


@dataclass(frozen=True)
class FieldError:
    field: str
    message: str
    incomplete: bool = (
        False  # True: field simply not filled in yet (no red text)
    )


@dataclass(frozen=True)
class FieldHint:
    field: str
    message: str


@dataclass(frozen=True)
class Evaluation:
    errors: tuple[FieldError, ...] = ()
    hints: tuple[FieldHint, ...] = ()
    line: LineInput | None = None
    result: LineResult | None = None
    view: ResultView | None = None

    @property
    def valid(self) -> bool:
        return self.result is not None

    @property
    def incomplete_only(self) -> bool:
        return bool(self.errors) and all(e.incomplete for e in self.errors)


# ---- evaluation -----------------------------------------------------------

_MONEY_FIELDS = (
    ("regular_price", True),
    ("website_price", True),
    ("coupon", False),
    ("manager_value", False),
)


def _need(read: MoneyRead) -> Decimal:
    if read.value is None:  # unreachable once errors were checked
        raise ValueError("money value missing")
    return read.value


def evaluate_line(form: LineForm) -> Evaluation:
    texts = {
        "regular_price": form.regular_price,
        "website_price": form.website_price,
        "coupon": form.coupon,
        "manager_value": form.manager_value,
    }
    reads = {field: read_money(texts[field]) for field, _ in _MONEY_FIELDS}

    hints = tuple(
        FieldHint(field, read.hint)
        for field, read in reads.items()
        if read.hint is not None
    )
    name = " ".join(form.product_name.split())
    name_errors = (
        ()
        if name
        else (FieldError("product_name", "Enter a product name.", True),)
    )
    money_errors = tuple(
        FieldError(
            field, reads[field].error or "", incomplete=reads[field].empty
        )
        for field, required in _MONEY_FIELDS
        if reads[field].error is not None
        and (required or not reads[field].empty)
    )
    errors = name_errors + money_errors
    if errors:
        return Evaluation(errors=errors, hints=hints)

    manager_read = reads["manager_value"]
    manager_value = None if manager_read.empty else _need(manager_read)
    line = LineInput(
        product_name=name,
        quantity=form.quantity,
        regular_price=_need(reads["regular_price"]),
        website_price=_need(reads["website_price"]),
        coupon=ZERO if reads["coupon"].empty else _need(reads["coupon"]),
        gift_selected=form.gift_selected,
        gift_name=form.gift_name.strip() or None,
        manager_value=manager_value,
        manager_mode=form.manager_mode if manager_value is not None else None,
        product_id=form.product_id,
    )
    match calculate_line(line):
        case Ok(result):
            return Evaluation(
                hints=hints,
                line=line,
                result=result,
                view=present_result(line, result),
            )
        case Err(problems):
            return Evaluation(
                errors=tuple(FieldError(p.field, p.message) for p in problems),
                hints=hints,
                line=line,
            )
    raise AssertionError("unreachable")  # pragma: no cover


# ---- presentation ---------------------------------------------------------


def _money_row(label: str, amount: Decimal) -> Row:
    return Row(
        label,
        format_try(amount),
        f"Exact value: {format_decimal_exact(amount)}",
    )


def present_result(line: LineInput, r: LineResult) -> ResultView:
    prices = Section(
        "Prices",
        (
            Row("Quantity", str(r.quantity)),
            _money_row("Regular price (unit)", line.regular_price),
            _money_row("Website discounted price (unit)", line.website_price),
            _money_row("Additional coupon (unit)", line.coupon),
            _money_row(
                "Effective website price (unit)", r.effective_website_unit
            ),
            _money_row("Regular total", r.regular_total),
            _money_row("Website discounted total", r.website_total),
            _money_row("Coupon total", r.coupon_total),
            _money_row("Effective website total", r.effective_website_total),
        ),
    )

    gift_rows = (
        (Row("Gift", line.gift_name or "(no gift name)"),)
        if line.gift_selected
        else ()
    )
    ten = Section(
        "Standard 10% scenario",
        (
            *gift_rows,
            Row(
                "Discount base",
                "Regular price (gift selected)"
                if line.gift_selected
                else "Effective website price (no gift)",
            ),
            _money_row("Base (unit)", r.ten_pct_base),
            _money_row("10% discount (unit)", r.ten_pct_discount_unit),
            _money_row("Resulting unit price", r.ten_pct_unit),
            Row("Quantity", str(r.quantity)),
            _money_row("Resulting line total", r.ten_pct_total),
        ),
    )

    manager: tuple[Section, ...] = ()
    if (
        r.manager_line_total is not None
        and r.manager_unit is not None
        and r.manager_mode is not None
    ):
        is_line = r.manager_mode is ManagerMode.LINE
        manager = (
            Section(
                "Manager-provided value",
                (
                    Row(
                        "Value mode",
                        "Total line price" if is_line else "Unit price",
                    ),
                    _money_row(
                        "Entered value",
                        r.manager_line_total if is_line else r.manager_unit,
                    ),
                    _money_row("Line total", r.manager_line_total),
                    _money_row(
                        "Unit value (derived, display only)"
                        if is_line
                        else "Unit value",
                        r.manager_unit,
                    ),
                ),
                note="Used exactly as entered. Not converted to a percentage.",
            ),
        )

    if r.pos_amount is None or r.manager_line_total is None:
        pos_rows = (Row("Result", "n/a: enter a manager value"),)
    else:
        pos_rows = (
            _money_row("Regular total", r.regular_total),
            _money_row("Normal website discounted total", r.website_total),
            _money_row("Manager line total", r.manager_line_total),
            _money_row("POS-entry amount", r.pos_amount),
        )
    pos = Section(
        POS_LABEL,
        pos_rows,
        note=(
            "Informational only. Not an official or manager-approved POS instruction. "
            "The additional coupon is not part of this formula."
        ),
    )

    return ResultView(
        sections=(prices, ten, *manager, pos),
        warnings=tuple(w.message for w in r.warnings),
        explanation=_explain(line, r),
    )


def _explain(line: LineInput, r: LineResult) -> tuple[str, ...]:
    t = format_try
    q = r.quantity
    base_name = (
        "regular price (gift selected)"
        if line.gift_selected
        else "effective website price (no gift)"
    )
    steps = [
        f"Effective website price = {t(line.website_price)} − {t(line.coupon)}"
        f" = {t(r.effective_website_unit)}",
        f"10% base = {base_name} = {t(r.ten_pct_base)}",
        f"10% discount = {t(r.ten_pct_base)} × 10% = {t(r.ten_pct_discount_unit)}",
        f"Scenario unit price = {t(r.ten_pct_base)} − {t(r.ten_pct_discount_unit)}"
        f" = {t(r.ten_pct_unit)}",
        f"Scenario line total = {t(r.ten_pct_unit)} × {q} = {t(r.ten_pct_total)}",
    ]
    if r.manager_line_total is not None and r.manager_unit is not None:
        if r.manager_mode is ManagerMode.LINE:
            steps.append(
                f"Manager line total = {t(r.manager_line_total)} "
                "(entered as the total for the whole line)"
            )
            steps.append(
                f"Manager unit value = {t(r.manager_line_total)} ÷ {q} = {t(r.manager_unit)} "
                "(derived; rounded for display only)"
            )
        else:
            steps.append(
                f"Manager line total = {t(r.manager_unit)} × {q} = {t(r.manager_line_total)}"
            )
        if r.pos_amount is not None:
            steps.append(
                f"POS-entry amount = ({t(r.regular_total)} − {t(r.website_total)})"
                f" + {t(r.manager_line_total)} = {t(r.pos_amount)}"
                "  (normal website total; the coupon is not used)"
            )
    return tuple(steps)
