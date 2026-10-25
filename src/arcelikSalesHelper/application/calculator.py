"""Raw form text -> validated LineInput -> LineResult -> display model.

Pure: the UI only collects strings, calls ``evaluate_line`` and renders the
returned ``ResultView``.  All numbers shown come from ``LineResult``; nothing is
recomputed here (only formatted).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.domain.arith import ZERO
from arcelikSalesHelper.domain.formatting import (
    format_decimal_exact,
    format_try,
)
from arcelikSalesHelper.domain.models import (
    POS_LABEL,
    GiftOption,
    LineInput,
    LineResult,
    ManagerMode,
    TotalValue,
    TransactionResult,
    WebsiteOption,
)
from arcelikSalesHelper.domain.money import parse_money_ex
from arcelikSalesHelper.domain.pricing import (
    build_options,
    calculate_line,
    calculate_transaction,
)
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
    explanation: tuple[str, ...]
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
    ("website_price", True),
    ("coupon", False),
    ("manager_value", False),
)


def _need(read: MoneyRead) -> Decimal:
    if read.value is None:  # unreachable once errors were checked
        raise ValueError("money value missing")
    return read.value


def evaluate_line(form: LineForm, line_index: int = 0) -> Evaluation:
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


def present_result(line: LineInput, r: LineResult) -> ResultView:
    prices = Section(
        T.SEC_PRICES,
        (
            Row(T.LBL_QUANTITY, str(r.quantity)),
            _money_row(T.LBL_REGULAR_UNIT, line.regular_price),
            _money_row(T.LBL_WEBSITE_UNIT, line.website_price),
            _money_row(T.LBL_COUPON_UNIT, line.coupon),
            _money_row(T.LBL_EFFECTIVE_WEBSITE_UNIT, r.effective_website_unit),
            _money_row(T.LBL_REGULAR_TOTAL, r.regular_total),
            _money_row(T.LBL_WEBSITE_TOTAL, r.website_total),
            _money_row(T.LBL_COUPON_TOTAL, r.coupon_total),
            _money_row(T.LBL_EFFECTIVE_WEBSITE_TOTAL, r.effective_website_total),
        ),
    )

    gift_rows = (
        (Row(T.LBL_GIFT, line.gift_name or T.NO_GIFT_NAME),)
        if line.gift_selected
        else ()
    )
    ten = Section(
        T.SEC_TEN,
        (
            *gift_rows,
            Row(
                T.LBL_DISCOUNT_BASE,
                T.VAL_BASE_REGULAR_GIFT
                if line.gift_selected
                else T.VAL_BASE_EFFECTIVE_NOGIFT,
            ),
            _money_row(T.LBL_BASE_UNIT, r.ten_pct_base),
            _money_row(T.LBL_TEN_DISCOUNT_UNIT, r.ten_pct_discount_unit),
            _money_row(T.LBL_TEN_RESULT_UNIT, r.ten_pct_unit),
            Row(T.LBL_QUANTITY, str(r.quantity)),
            _money_row(T.LBL_TEN_RESULT_TOTAL, r.ten_pct_total),
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
                T.SEC_MANAGER,
                (
                    Row(T.LBL_VALUE_MODE, T.MODE_LINE if is_line else T.MODE_UNIT),
                    _money_row(
                        T.LBL_ENTERED_VALUE,
                        r.manager_line_total if is_line else r.manager_unit,
                    ),
                    _money_row(T.LBL_LINE_TOTAL, r.manager_line_total),
                    _money_row(
                        T.LBL_UNIT_VALUE_DERIVED if is_line else T.LBL_UNIT_VALUE,
                        r.manager_unit,
                    ),
                ),
                note=T.NOTE_MANAGER_SECTION,
            ),
        )

    pos_rows: tuple[Row, ...]
    if r.pos_amount is None or r.manager_line_total is None:
        pos_rows = (Row(T.LBL_RESULT, T.POS_MISSING_MANAGER),)
    else:
        pos_rows = (
            _money_row(T.LBL_REGULAR_TOTAL, r.regular_total),
            _money_row(T.LBL_POS_NORMAL_WEBSITE_TOTAL, r.website_total),
            _money_row(T.LBL_MANAGER_LINE_TOTAL, r.manager_line_total),
            _money_row(T.LBL_POS_AMOUNT, r.pos_amount),
        )
    pos = Section(POS_LABEL, pos_rows, note=T.NOTE_POS)

    website_opt, gift_opt = build_options(line, r)
    has_manager = r.manager_line_total is not None
    card = CardView(
        prices=prices,
        website_option=_website_section(website_opt, has_manager),
        gift_option=(
            None
            if gift_opt is None
            else _gift_section(gift_opt, line, has_manager)
        ),
        pos=pos,
    )
    return ResultView(
        sections=(prices, ten, *manager, pos),
        warnings=tuple(w.message for w in r.warnings),
        explanation=_explain(line, r),
        card=card,
    )


def _explain(line: LineInput, r: LineResult) -> tuple[str, ...]:
    t = format_try
    q = r.quantity
    base_name = (
        T.EXPLAIN_BASE_REGULAR_GIFT
        if line.gift_selected
        else T.EXPLAIN_BASE_EFFECTIVE_NOGIFT
    )
    steps = [
        T.explain_effective(
            t(line.website_price), t(line.coupon), t(r.effective_website_unit)
        ),
        T.explain_ten_base(base_name, t(r.ten_pct_base)),
        T.explain_ten_discount(t(r.ten_pct_base), t(r.ten_pct_discount_unit)),
        T.explain_scenario_unit(
            t(r.ten_pct_base), t(r.ten_pct_discount_unit), t(r.ten_pct_unit)
        ),
        T.explain_scenario_total(t(r.ten_pct_unit), q, t(r.ten_pct_total)),
    ]
    if r.manager_line_total is not None and r.manager_unit is not None:
        if r.manager_mode is ManagerMode.LINE:
            steps.append(T.explain_manager_line(t(r.manager_line_total)))
            steps.append(
                T.explain_manager_unit_derived(
                    t(r.manager_line_total), q, t(r.manager_unit)
                )
            )
        else:
            steps.append(
                T.explain_manager_unit(
                    t(r.manager_unit), q, t(r.manager_line_total)
                )
            )
        if r.pos_amount is not None:
            steps.append(
                T.explain_pos(
                    t(r.regular_total),
                    t(r.website_total),
                    t(r.manager_line_total),
                    t(r.pos_amount),
                )
            )
    return tuple(steps)


# ---- option panels --------------------------------------------------------

def _option_manager(
    mode: ManagerMode | None,
    unit: Decimal | None,
    total: Decimal | None,
    has_manager: bool,
) -> tuple[tuple[Row, ...], str | None]:
    """The manager value is shown on exactly one option, never on both."""
    if mode is not None and unit is not None and total is not None:
        is_line = mode is ManagerMode.LINE
        rows = (
            Row(
                T.LBL_MANAGER_MODE,
                T.MODE_LINE if is_line else T.MODE_UNIT,
            ),
            _money_row(T.LBL_MANAGER_LINE_TOTAL, total),
            _money_row(
                T.LBL_MANAGER_UNIT_DERIVED if is_line else T.LBL_MANAGER_UNIT,
                unit,
            ),
        )
        return rows, T.NOTE_MANAGER_OPTION
    if has_manager:
        return (Row(T.LBL_MANAGER_VALUE, T.VAL_SHOWN_ON_OTHER),), None
    return (), None


def _website_section(w: WebsiteOption, has_manager: bool) -> Section:
    manager_rows, note = _option_manager(
        w.manager_mode, w.manager_unit, w.manager_line_total, has_manager
    )
    return Section(
        T.SEC_WEBSITE_OPTION,
        (
            _money_row(T.LBL_WEBSITE_TOTAL, w.website_total),
            _money_row(T.LBL_COUPON_TOTAL, w.coupon_total),
            _money_row(T.LBL_EFFECTIVE_WEBSITE_UNIT, w.effective_unit),
            _money_row(T.LBL_EFFECTIVE_WEBSITE_TOTAL, w.effective_total),
            Row(T.LBL_TEN_BASE, T.VAL_BASE_EFFECTIVE),
            _money_row(T.LBL_TEN_BASE_UNIT, w.ten_pct_base),
            _money_row(T.LBL_TEN_DISCOUNT_UNIT, w.ten_pct_discount_unit),
            _money_row(T.LBL_TEN_UNIT_PRICE, w.ten_pct_unit),
            _money_row(T.LBL_TEN_LINE_TOTAL, w.ten_pct_total),
            *manager_rows,
        ),
        note=note,
    )


def _gift_section(
    g: GiftOption, line: LineInput, has_manager: bool
) -> Section:
    manager_rows, manager_note = _option_manager(
        g.manager_mode, g.manager_unit, g.manager_line_total, has_manager
    )
    notes = [] if line.gift_selected else [T.NOTE_GIFT_NOT_SELECTED]
    if manager_note:
        notes.append(manager_note)
    return Section(
        T.SEC_GIFT_OPTION,
        (
            Row(T.LBL_GIFT, g.gift_name or T.NO_GIFT_NAME),
            _money_row(T.LBL_REGULAR_TOTAL, g.regular_total),
            Row(T.LBL_TEN_BASE, T.VAL_BASE_REGULAR),
            _money_row(T.LBL_TEN_BASE_UNIT, g.ten_pct_base),
            _money_row(T.LBL_TEN_DISCOUNT_UNIT, g.ten_pct_discount_unit),
            _money_row(T.LBL_TEN_UNIT_PRICE, g.ten_pct_unit),
            _money_row(T.LBL_TEN_LINE_TOTAL, g.ten_pct_total),
            *manager_rows,
        ),
        note=" ".join(notes) or None,
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
    main = Section(
        T.SEC_TOTALS,
        (
            Row(T.LBL_LINES, str(len(result.lines))),
            _total_row(T.LBL_TOTAL_REGULAR, t.regular, T.MISSING_REGULAR),
            _total_row(T.LBL_TOTAL_WEBSITE, t.website, T.MISSING_WEBSITE),
            _total_row(
                T.LBL_TOTAL_EFFECTIVE, t.effective_website, T.MISSING_WEBSITE
            ),
            _total_row(T.LBL_TOTAL_TEN, t.ten_pct, T.MISSING_PRICE),
            _total_row(T.LBL_TOTAL_MANAGER, t.manager, T.MISSING_MANAGER),
        ),
        note=T.NOTE_TOTALS,
    )
    pos = Section(
        POS_LABEL,
        (_total_row(T.LBL_TOTAL_POS, t.pos, T.MISSING_MANAGER),),
        note=T.NOTE_TOTAL_POS,
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
