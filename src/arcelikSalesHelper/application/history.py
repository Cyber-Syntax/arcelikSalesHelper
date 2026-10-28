"""Snapshot building and reading. Pure: no Qt, no sqlite3.

A snapshot stores, per line, the entered text, the exact normalized inputs, the
exact LineResult and the *rendered* sections that were on screen. The history
view is rebuilt from these stored strings only, so later changes to products,
formulas or the formatter cannot change what an old calculation shows.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.domain.formatting import format_decimal_exact
from arcelikSalesHelper.domain.models import (
    POS_LABEL,
    ConfirmationState,
    LineInput,
    LineResult,
    LineWarning,
)
from arcelikSalesHelper.domain.result import Err, Ok, Result

from .calculator import (
    LineForm,
    ResultView,
    Row,
    Section,
    TransactionEvaluation,
)

_CORRUPT = T.HISTORY_CORRUPT

# ---- records (what is written to / read from the database) ------------------


@dataclass(frozen=True)
class LineRecord:
    line_index: int
    product_id: int | None
    product_name: str
    quantity: int
    regular_price: str
    website_discounted_price: str
    gift_selected: bool
    gift_name: str | None
    manager_value_entered: str | None  # text exactly as typed
    manager_mode: str | None
    pos_calculation_mode: str
    manager_line_total: str | None
    manager_unit: str | None
    result_json: str
    entered_json: str


@dataclass(frozen=True)
class SnapshotRecord:
    created_at: str
    app_version: str
    schema_version: int
    totals_json: str
    confirmation_state: str
    warnings_json: str
    lines: tuple[LineRecord, ...]
    id: int | None = None
    customer_name: str | None = None


@dataclass(frozen=True)
class SnapshotHeader:
    id: int
    created_at: str
    line_count: int
    product_names: tuple[str, ...]
    totals_json: str
    customer_name: str | None = None


# ---- serialisation ----------------------------------------------------------


def to_utc_iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_jsonable(value: object) -> object:
    """Exact, lossless conversion: Decimals become plain-decimal strings."""
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Decimal):
        return format_decimal_exact(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: to_jsonable(getattr(value, f.name)) for f in fields(value)
        }
    if isinstance(value, Mapping):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [to_jsonable(v) for v in value]
    raise TypeError(f"cannot serialise {type(value).__name__}")


def _dumps(value: object) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=False, sort_keys=True)


# ---- building ---------------------------------------------------------------


def _pos_total_text(sections: tuple[Section, ...]) -> str:
    for section in sections:
        if section.title == POS_LABEL and section.rows:
            return section.rows[0].value
    return ""


def _line_record(
    index: int,
    form: LineForm,
    line: LineInput,
    result: LineResult,
    view: ResultView,
) -> LineRecord:
    card = view.card
    body = {
        "view": {
            "prices": card.prices,
            "website_option": card.website_option,
            "gift_option": card.gift_option,
            "pos": card.pos,
            "warnings": view.warnings,
        },
    }
    has_manager = line.manager_value is not None
    return LineRecord(
        line_index=index,
        product_id=line.product_id,
        product_name=line.product_name,
        quantity=line.quantity,
        regular_price=format_decimal_exact(line.regular_price),
        website_discounted_price=format_decimal_exact(line.website_discounted_price),
        gift_selected=line.gift_selected,
        gift_name=line.gift_name,
        manager_value_entered=(form.manager_value.strip() or format_decimal_exact(line.manager_value))
        if has_manager
        else None,
        manager_mode=None
        if result.manager_mode is None
        else result.manager_mode.value,
        pos_calculation_mode=line.pos_calculation_mode.value,
        manager_line_total=(
            None
            if result.manager_line_total is None
            else format_decimal_exact(result.manager_line_total)
        ),
        manager_unit=(
            None
            if result.manager_unit is None
            else format_decimal_exact(result.manager_unit)
        ),
        result_json=_dumps(body),
        entered_json="{}",
    )


def build_snapshot(
    evaluation: TransactionEvaluation,
    *,
    created_at: str,
    app_version: str,
    schema_version: int,
    customer_name: str | None = None,
) -> Result[SnapshotRecord, str]:
    """Pure. Only a fully valid evaluation can become a snapshot."""
    result = evaluation.result
    if result is None or len(evaluation.forms) != len(evaluation.lines):
        return Err(T.HISTORY_ONLY_COMPLETE)

    lines: list[LineRecord] = []
    warnings: list[LineWarning] = []
    for index, (form, ev) in enumerate(
        zip(evaluation.forms, evaluation.lines, strict=True)
    ):
        if ev.line is None or ev.result is None or ev.view is None:
            return Err(T.HISTORY_ONLY_COMPLETE)
        lines.append(_line_record(index, form, ev.line, ev.result, ev.view))
        warnings.extend(ev.result.warnings)

    totals = {
        "sections": evaluation.totals_sections,
        "pos_total_text": _pos_total_text(evaluation.totals_sections),
    }
    return Ok(
        SnapshotRecord(
            created_at=created_at,
            app_version=app_version,
            schema_version=schema_version,
            totals_json=_dumps(totals),
            confirmation_state=ConfirmationState.POS_UNVERIFIED.value,
            warnings_json=_dumps(warnings),
            lines=tuple(lines),
            customer_name=(" ".join(customer_name.split()) or None)
            if customer_name is not None
            else None,
        )
    )


# ---- reading ----------------------------------------------------------------


@dataclass(frozen=True)
class StoredWarning:
    line_index: int
    code: str
    message: str


@dataclass(frozen=True)
class StoredLine:
    line_index: int
    product_name: str
    quantity: int
    gift_selected: bool
    gift_name: str | None
    prices: Section
    website_option: Section
    gift_option: Section | None
    pos: Section
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class StoredSnapshot:
    id: int
    created_at: str
    app_version: str
    schema_version: int
    confirmation_state: str
    totals_sections: tuple[Section, ...]
    warnings: tuple[StoredWarning, ...]
    lines: tuple[StoredLine, ...]
    customer_name: str | None = None


@dataclass(frozen=True)
class HistorySummary:
    id: int
    created_at: str
    line_count: int
    products_text: str
    pos_total: str
    customer_name: str | None = None


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)


def _section(data: Any) -> Section:
    return Section(
        title=str(data["title"]),
        rows=tuple(
            Row(str(r["label"]), str(r["value"]), _opt_str(r.get("tooltip")))
            for r in data["rows"]
        ),
        note=_opt_str(data.get("note")),
    )


def _parse_line(record: LineRecord) -> StoredLine:
    body = json.loads(record.result_json)
    view = body["view"]
    gift = view["gift_option"]
    return StoredLine(
        line_index=record.line_index,
        product_name=record.product_name,
        quantity=record.quantity,
        gift_selected=record.gift_selected,
        gift_name=record.gift_name,
        prices=_section(view["prices"]),
        website_option=_section(view["website_option"]),
        gift_option=None if gift is None else _section(gift),
        pos=_section(view["pos"]),
        warnings=tuple(str(w) for w in view["warnings"]),
    )


def parse_snapshot(record: SnapshotRecord) -> Result[StoredSnapshot, str]:
    """Rebuild the display model from stored rows only. Never recomputes anything."""
    if record.id is None:
        return Err(_CORRUPT)
    try:
        totals = json.loads(record.totals_json)
        warnings = json.loads(record.warnings_json)
        return Ok(
            StoredSnapshot(
                id=record.id,
                created_at=record.created_at,
                app_version=record.app_version,
                schema_version=record.schema_version,
                confirmation_state=record.confirmation_state,
                totals_sections=tuple(_section(s) for s in totals["sections"]),
                warnings=tuple(
                    StoredWarning(
                        int(w["line_index"]), str(w["code"]), str(w["message"])
                    )
                    for w in warnings
                ),
                lines=tuple(_parse_line(line) for line in record.lines),
                customer_name=record.customer_name,
            )
        )
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return Err(_CORRUPT)


def summarize(header: SnapshotHeader) -> HistorySummary:
    try:
        pos = str(json.loads(header.totals_json)["pos_total_text"])
    except (KeyError, TypeError, ValueError):
        pos = "?"
    return HistorySummary(
        header.id,
        header.created_at,
        header.line_count,
        ", ".join(header.product_names),
        pos,
        header.customer_name,
    )


def confirmation_text(state: str) -> str:
    if state == ConfirmationState.POS_UNVERIFIED.value:
        return T.confirmation_pos_unverified()
    return T.confirmation_other(state)
