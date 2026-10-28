"""Raw form text -> validated LineInput -> LineResult -> display model.

Pure: the UI only collects strings, calls ``evaluate_line`` and renders the
returned ``ResultView``.  All numbers shown come from ``LineResult``; nothing is
recomputed here (only formatted).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.domain.formatting import format_decimal_exact, format_try
from arcelikSalesHelper.domain.models import (
    POS_LABEL,
    GiftOption,
    LineInput,
    LineResult,
    ManagerMode,
    PosCalculationMode,
    TotalValue,
    TransactionResult,
    WebsiteOption,
)
from arcelikSalesHelper.domain.money import parse_money_ex
from arcelikSalesHelper.domain.pricing import (
    build_options,
    calculate_line,
    calculate_transaction,
    effective_website_price,
)
from arcelikSalesHelper.domain.result import Err, Ok

# ---- input ----------------------------------------------------------------


@dataclass(frozen=True)
class LineForm:
    """Exactly what the widgets contain, as raw text."""

    product_name: str
    quantity: int = 1
    regular_price: str = ""
    website_discounted_price: str = ""
    gift_selected: bool = False
    gift_name: str = ""
    manager_value: str = ""
    manager_value_decimal: Decimal | None = None
    manager_mode: ManagerMode = ManagerMode.UNIT
    pos_calculation_mode: PosCalculationMode = PosCalculationMode.FIXED_AMOUNT
    product_id: int | None = None


@dataclass(frozen=True)
class MoneyRead:
    value: Decimal | None
    error: str | None
    hint: str | None
    empty: bool


def read_money(text: str) -> MoneyRead:
    if not text.strip():
        return MoneyRead(None, T.MONEY_EMPTY, None, True)
    match parse_money_ex(text):
        case Ok(parsed):
            hint = (
                T.money_ambiguous_hint(format_try(parsed.value))
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
class CardView:
    """What one line's result card shows (the 10% and manager details live in the options)."""

    prices: Section
    website_option: Section
    gift_option: (
        Section | None
    )  # None when the line has no gift selected or named
    pos: Section


@dataclass(frozen=True)
class ResultView:
    sections: tuple[Section, ...]
    warnings: tuple[str, ...]
    card: CardView


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
    ("website_discounted_price", True),
    ("manager_value", False),
)


def _need(read: MoneyRead) -> Decimal:
    if read.value is None:  # unreachable once errors were checked
        raise ValueError("money value missing")
    return read.value


def evaluate_line(form: LineForm, line_index: int = 0) -> Evaluation:
    texts = {
        "regular_price": form.regular_price,
        "website_discounted_price": form.website_discounted_price,
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
        else (FieldError("product_name", T.FIELD_PRODUCT_NAME_REQUIRED, True),)
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
    manager_value = (
        form.manager_value_decimal
        if form.manager_value_decimal is not None
        else None if manager_read.empty else _need(manager_read)
    )
    line = LineInput(
        product_name=name,
        quantity=form.quantity,
        regular_price=_need(reads["regular_price"]),
        website_discounted_price=_need(reads["website_discounted_price"]),
        gift_selected=form.gift_selected,
        gift_name=form.gift_name.strip() or None,
        manager_value=manager_value,
        manager_mode=form.manager_mode if manager_value is not None else None,
        pos_calculation_mode=form.pos_calculation_mode,
        product_id=form.product_id,
    )
    match calculate_line(line, line_index):
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
        T.exact_value_tooltip(format_decimal_exact(amount)),
    )


def _format_percentage(value: Decimal) -> str:
    exact = format_decimal_exact(value)
    return exact.rstrip("0").rstrip(".") if "." in exact else exact


def present_result(line: LineInput, r: LineResult) -> ResultView:
    website_unit = (
        Row(T.LBL_WEBSITE_UNIT, T.NO_WEBSITE_DISCOUNT)
        if line.website_discounted_price == 0
        else _money_row(T.LBL_WEBSITE_UNIT, effective_website_price(line))
    )
    website_total = (
        Row(T.LBL_WEBSITE_DISCOUNTED_TOTAL, T.NO_WEBSITE_DISCOUNT)
        if line.website_discounted_price == 0
        else _money_row(
            T.LBL_WEBSITE_DISCOUNTED_TOTAL, r.website_discounted_total
        )
    )
    prices = Section(
        T.SEC_PRICES,
        (
            Row(T.LBL_QUANTITY, str(r.quantity)),
            _money_row(T.LBL_REGULAR_UNIT, line.regular_price),
            website_unit,
            _money_row(T.LBL_REGULAR_TOTAL, r.regular_total),
            website_total,
            *(
                (_money_row(T.LBL_MANAGER_LINE_TOTAL, r.manager_line_total),)
                if r.manager_line_total is not None
                else ()
            ),
        ),
    )

    pos_rows: tuple[Row, ...] = ()
    if r.pos_amount is None or r.manager_line_total is None:
        pos_rows += (Row(T.LBL_POS_AMOUNT, T.POS_MISSING_MANAGER),)
    else:
        pos_rows += (_money_row(T.LBL_POS_AMOUNT, r.pos_amount),)
        if not line.gift_selected:
            formula = (
                T.POS_FORMULA_PERCENTAGE
                if line.pos_calculation_mode is PosCalculationMode.PERCENTAGE
                else T.POS_FORMULA_FIXED
            )
            mode_label = (
                T.POS_MODE_PERCENTAGE
                if line.pos_calculation_mode is PosCalculationMode.PERCENTAGE
                else T.POS_MODE_FIXED
            )
            pos_rows += (
                Row(T.FORM_POS_CALCULATION_MODE, mode_label),
                Row(T.POS_FORMULA_LABEL, formula),
            )
            if line.pos_calculation_mode is PosCalculationMode.PERCENTAGE:
                rate_text = (
                    T.NOT_AVAILABLE
                    if r.pos_discount_percentage is None
                    else f"{_format_percentage(r.pos_discount_percentage)}%"
                )
                pos_rows += (Row(T.LBL_POS_DISCOUNT_RATE, rate_text),)
    pos = Section(POS_LABEL, pos_rows)

    website_opt, gift_opt = build_options(line, r)
    card = CardView(
        prices=prices,
        website_option=_website_section(
            website_opt,
            no_website_discount=line.website_discounted_price == 0,
            discount_amount=r.discount_amount,
        ),
        gift_option=(
            None
            if gift_opt is None
            else _gift_section(gift_opt)
        ),
        pos=pos,
    )
    return ResultView(
        sections=(prices, pos),
        warnings=tuple(w.message for w in r.warnings),
        card=card,
    )


# ---- option panels --------------------------------------------------------

def _website_section(
    w: WebsiteOption,
    *,
    no_website_discount: bool,
    discount_amount: Decimal,
) -> Section:
    offer_label = (
        T.LBL_FIRST_PRICE_TEN_PERCENT
        if no_website_discount
        else T.LBL_WEBSITE_OFFER_TOTAL
    )
    return Section(
        T.SEC_WEBSITE_OPTION,
        (
            (
                Row(T.LBL_WEBSITE_DISCOUNTED_TOTAL, T.NO_WEBSITE_DISCOUNT)
                if no_website_discount
                else _money_row(
                    T.LBL_WEBSITE_DISCOUNTED_TOTAL,
                    w.website_discounted_total,
                )
            ),
            _money_row(T.LBL_DISCOUNT_AMOUNT, discount_amount),
            _money_row(offer_label, w.ten_pct_total),
        ),
    )


def _gift_section(g: GiftOption) -> Section:
    return Section(
        T.SEC_GIFT_OPTION,
        (
            Row(T.LBL_GIFT, g.gift_name or T.NO_GIFT_NAME),
            _money_row(T.LBL_REGULAR_TOTAL, g.regular_total),
            _money_row(T.LBL_FIRST_PRICE_TEN_PERCENT, g.ten_pct_total),
        ),
    )


# ---- transaction ----------------------------------------------------------


@dataclass(frozen=True)
class TransactionEvaluation:
    lines: tuple[Evaluation, ...]
    forms: tuple[LineForm, ...] = ()  # entered text, kept for the M5 snapshot
    result: TransactionResult | None = None
    totals_sections: tuple[Section, ...] = ()
    pending_reason: str | None = None  # why there are no totals

    @property
    def valid(self) -> bool:
        return self.result is not None


def _total_row(label: str, total: TotalValue, what: str) -> Row:
    if total.value is not None:
        return _money_row(label, total.value)
    numbers = ", ".join(str(i + 1) for i in total.missing_lines)
    return Row(
        label, T.total_missing(what, numbers, len(total.missing_lines) > 1)
    )


def present_totals(result: TransactionResult) -> tuple[Section, ...]:
    t = result.totals
    main = Section(T.SEC_PRICE_SCENARIOS, (
        Row(T.LBL_LINES, str(len(result.lines))),
        _total_row(T.LBL_TOTAL_REGULAR, t.regular, T.MISSING_PRICE),
        _total_row(T.LBL_TOTAL_WEBSITE, t.website_discounted, T.MISSING_PRICE),
        _total_row(T.LBL_TOTAL_DISCOUNT, t.discount_amount, T.MISSING_PRICE),
        _total_row(T.LBL_TOTAL_TEN, t.ten_pct, T.MISSING_PRICE),
        _total_row(T.LBL_TOTAL_FIFTEEN, t.fifteen_pct, T.MISSING_PRICE),
        _total_row(T.LBL_TOTAL_EIGHTEEN, t.eighteen_pct, T.MISSING_PRICE),
        _total_row(T.LBL_TOTAL_TWENTY, t.twenty_pct, T.MISSING_PRICE),
    ))
    pos = Section(
        POS_LABEL,
        (_total_row(T.LBL_TOTAL_POS, t.pos, T.MISSING_MANAGER),),
    )
    return (main, pos)


def evaluate_transaction(forms: Sequence[LineForm]) -> TransactionEvaluation:
    kept = tuple(forms)
    evals = tuple(evaluate_line(f, i) for i, f in enumerate(kept))
    if not evals:
        return TransactionEvaluation(
            evals, kept, pending_reason=T.PENDING_NO_LINES
        )
    bad = [str(i + 1) for i, e in enumerate(evals) if not e.valid]
    if bad:
        return TransactionEvaluation(
            evals,
            kept,
            pending_reason=T.pending_lines(", ".join(bad)),
        )
    inputs = [e.line for e in evals if e.line is not None]
    match calculate_transaction(inputs):
        case Ok(result):
            return TransactionEvaluation(
                evals, kept, result, present_totals(result)
            )
        case Err(problems):
            return TransactionEvaluation(
                evals, kept, pending_reason=problems[0].message
            )
    raise AssertionError("unreachable")  # pragma: no cover
