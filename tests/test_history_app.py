import json
from dataclasses import replace
from decimal import Decimal as D

import pytest

from arcelikSalesHelper.application.calculator import evaluate_transaction
from arcelikSalesHelper.application.history import (
    SnapshotHeader,
    build_snapshot,
    confirmation_text,
    parse_snapshot,
    summarize,
    to_jsonable,
)
from arcelikSalesHelper.domain.arith import div
from arcelikSalesHelper.domain.models import POS_LABEL, ManagerMode
from arcelikSalesHelper.domain.result import Err, Ok

from .test_transaction_app import form, two_forms


def snapshot(forms=None):  # type: ignore[no-untyped-def]
    ev = evaluate_transaction(two_forms() if forms is None else forms)
    built = build_snapshot(
        ev,
        created_at="2026-01-01T12:00:00Z",
        app_version="0.1.0",
        schema_version=2,
    )
    assert isinstance(built, Ok), built
    return ev, built.value


# ---- serialisation ----------------------------------------------------------
def test_to_jsonable_supports_nested_mappings() -> None:
    assert to_jsonable({"nested": {"amount": D("1.20")}}) == {
        "nested": {"amount": "1.20"}
    }


def test_to_jsonable_is_exact_and_covers_enums_and_nesting() -> None:
    assert to_jsonable(D("1E+2")) == "100"
    assert to_jsonable(D("0.10")) == "0.10"
    assert to_jsonable(ManagerMode.LINE) == "line"
    assert to_jsonable((D(1), None, True, 3, "x")) == ["1", None, True, 3, "x"]


def test_to_jsonable_rejects_binary_floats() -> None:
    with pytest.raises(TypeError):
        to_jsonable(1.5)


# ---- build ------------------------------------------------------------------


def test_snapshot_columns_hold_normalized_values_and_entered_text() -> None:
    _, rec = snapshot()
    first, second = rec.lines
    assert (first.line_index, first.product_name, first.quantity) == (
        0,
        "Fridge",
        1,
    )
    assert D(first.regular_price) == D(5000) and D(first.website_discounted_price) == D(
        4000
    )
    assert (
        first.manager_value_entered == "3.000,00"
        and first.manager_mode == "unit"
    )
    assert D(first.manager_line_total or "") == D(3000)

    assert (
        second.quantity == 3
        and second.gift_selected
        and second.gift_name == "Vacuum"
    )
    assert D(second.manager_line_total or "") == D(13500)
    assert D(second.manager_unit or "") == D(4500)
    assert json.loads(second.entered_json)["regular_price"] == "6.000,00"


def test_snapshot_level_fields() -> None:
    _, rec = snapshot()
    assert rec.confirmation_state == "pos_unverified"
    assert (rec.app_version, rec.schema_version) == ("0.1.0", 2)
    assert json.loads(rec.totals_json)["pos_total_text"] == "20.500,00 TL"
    assert json.loads(rec.warnings_json) == []


def test_warnings_are_stored_with_their_line_index() -> None:
    _, rec = snapshot(
        [form(manager_value="4.500,00")]
    )  # above the 4.000 website price
    stored = json.loads(rec.warnings_json)
    assert [(w["line_index"], w["code"]) for w in stored] == [
        (0, "manager_exceeds_website")
    ]


def test_line_mode_unit_value_is_stored_exactly_not_rounded() -> None:
    _, rec = snapshot(
        [form(quantity=3, manager_value="10", manager_mode=ManagerMode.LINE)]
    )
    line = rec.lines[0]
    assert D(line.manager_line_total or "") == D(10)
    assert D(line.manager_unit or "") == div(D(10), D(3))
    assert D(json.loads(line.result_json)["result"]["manager_unit"]) == div(
        D(10), D(3)
    )


def test_only_valid_evaluations_can_be_saved() -> None:
    for forms in (
        [],
        [form(website_discounted_price="bad")],
        [form(), form(regular_price="")],
    ):
        ev = evaluate_transaction(forms)
        built = build_snapshot(
            ev, created_at="t", app_version="v", schema_version=2
        )
        assert isinstance(built, Err)


# ---- read -------------------------------------------------------------------


def test_stored_view_equals_what_was_displayed() -> None:
    ev, rec = snapshot()
    parsed = parse_snapshot(replace(rec, id=7))
    assert isinstance(parsed, Ok)
    stored = parsed.value
    assert stored.id == 7 and stored.totals_sections == ev.totals_sections
    for stored_line, line_eval in zip(stored.lines, ev.lines, strict=True):
        assert line_eval.view is not None
        card = line_eval.view.card
        assert stored_line.prices == card.prices
        assert stored_line.website_option == card.website_option
        assert stored_line.gift_option == card.gift_option
        assert stored_line.pos == card.pos
        assert stored_line.explanation == line_eval.view.explanation
    assert stored.lines[0].gift_option is None  # no gift on line 1
    assert stored.lines[1].gift_option is not None


def test_entered_section_shows_text_as_typed() -> None:
    _, rec = snapshot()
    parsed = parse_snapshot(replace(rec, id=1))
    assert isinstance(parsed, Ok)
    rows = {r.label: r.value for r in parsed.value.lines[0].entered.rows}
    assert rows["Normal fiyat"] == "5.000,00"
    assert rows["Yönetici değer modu"] == "Birim fiyat"


def test_stored_warnings_roundtrip() -> None:
    _, rec = snapshot([form(manager_value="4.500,00")])
    parsed = parse_snapshot(replace(rec, id=1))
    assert isinstance(parsed, Ok)
    assert [(w.line_index, w.code) for w in parsed.value.warnings] == [
        (0, "manager_exceeds_website")
    ]


@pytest.mark.parametrize("field", ["totals_json", "warnings_json"])
def test_corrupt_snapshot_json_is_a_typed_error(field: str) -> None:
    _, rec = snapshot()
    assert isinstance(parse_snapshot(replace(rec, id=1, **{field: "{"})), Err)


def test_corrupt_line_json_and_missing_id_are_typed_errors() -> None:
    _, rec = snapshot()
    bad_line = replace(rec.lines[0], result_json='{"view": 1}')
    assert isinstance(
        parse_snapshot(replace(rec, id=1, lines=(bad_line,))), Err
    )
    assert isinstance(parse_snapshot(rec), Err)  # id is None


def test_summary_and_confirmation_text() -> None:
    _, rec = snapshot()
    header = SnapshotHeader(
        3, rec.created_at, 2, ("Fridge", "Washer"), rec.totals_json
    )
    summary = summarize(header)
    assert (summary.products_text, summary.pos_total) == (
        "Fridge, Washer",
        "20.500,00 TL",
    )
    assert summarize(replace(header, totals_json="{")).pos_total == "?"
    assert POS_LABEL in confirmation_text("pos_unverified")
    assert "mystery" in confirmation_text("mystery")
