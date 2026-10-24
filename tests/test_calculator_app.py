from decimal import Decimal as D

from arcelikSalesHelper.application.calculator import LineForm, evaluate_line
from arcelikSalesHelper.domain.models import POS_LABEL, ManagerMode


def valid_form(**kw: object) -> LineForm:
    base: dict[str, object] = dict(
        product_name="Fridge",
        regular_price="5.000,00",
        website_price="4.000,00",
    )
    base.update(kw)
    return LineForm(**base)  # type: ignore[arg-type]


def test_valid_one_off_with_coupon_and_manager_value() -> None:
    ev = evaluate_line(valid_form(coupon="50", manager_value="3.000,00"))
    assert ev.valid and ev.result is not None and ev.line is not None
    assert ev.result.effective_website_unit == D(3950)
    assert ev.result.pos_amount == D(4000)
    assert ev.line.manager_mode is ManagerMode.UNIT


def test_view_has_the_exact_pos_label_and_formatted_values() -> None:
    ev = evaluate_line(valid_form(coupon="50", manager_value="3.000,00"))
    assert ev.view is not None
    titles = [s.title for s in ev.view.sections]
    assert POS_LABEL in titles
    pos = next(s for s in ev.view.sections if s.title == POS_LABEL)
    assert ("POS-entry amount", "4.000,00 TL") in [
        (r.label, r.value) for r in pos.rows
    ]
    assert any("3.950,00 TL" in line for line in ev.view.explanation)


def test_empty_manager_value_means_no_manager_section_and_pos_na() -> None:
    ev = evaluate_line(valid_form())
    assert ev.view is not None and ev.line is not None
    assert (
        ev.line.manager_mode is None
    )  # mode is dropped when there is no value
    assert "Manager-provided value" not in [s.title for s in ev.view.sections]
    pos = next(s for s in ev.view.sections if s.title == POS_LABEL)
    assert pos.rows[0].value.startswith("n/a")


def test_total_line_mode_is_passed_through() -> None:
    ev = evaluate_line(
        valid_form(
            quantity=3,
            manager_value="12.000,00",
            manager_mode=ManagerMode.LINE,
        )
    )
    assert ev.result is not None
    assert ev.result.manager_line_total == D(12000)
    assert ev.result.manager_unit == D(4000)


def test_unfilled_form_is_incomplete_not_an_error_display() -> None:
    ev = evaluate_line(LineForm(product_name=""))
    assert not ev.valid and ev.incomplete_only
    assert {e.field for e in ev.errors} == {
        "product_name",
        "regular_price",
        "website_price",
    }
    assert ev.view is None


def test_bad_price_text_is_a_real_error() -> None:
    ev = evaluate_line(valid_form(website_price="abc"))
    assert not ev.valid and not ev.incomplete_only
    assert [(e.field, e.incomplete) for e in ev.errors] == [
        ("website_price", False)
    ]


def test_empty_optional_fields_are_fine_but_bad_optional_text_is_not() -> None:
    assert evaluate_line(valid_form(coupon="")).valid
    ev = evaluate_line(valid_form(coupon="x"))
    assert [e.field for e in ev.errors] == ["coupon"]
    assert not evaluate_line(valid_form(manager_value="-5")).valid


def test_domain_validation_errors_are_mapped_to_fields() -> None:
    ev = evaluate_line(valid_form(coupon="5.000,00"))
    assert [(e.field, e.incomplete) for e in ev.errors] == [("coupon", False)]
    assert ev.view is None and ev.result is None


def test_ambiguous_thousands_input_produces_a_hint_but_still_calculates() -> (
    None
):
    ev = evaluate_line(
        valid_form(regular_price="5.000", website_price="4.000")
    )
    assert ev.valid
    assert {h.field for h in ev.hints} == {"regular_price", "website_price"}
    assert "5.000,00 TL" in ev.hints[0].message


def test_gift_name_is_trimmed_and_blank_becomes_none() -> None:
    assert (
        evaluate_line(valid_form(gift_name="  Vacuum ")).line.gift_name
        == "Vacuum"
    )  # type: ignore[union-attr]
    assert evaluate_line(valid_form(gift_name="   ")).line.gift_name is None  # type: ignore[union-attr]


def test_manager_above_website_total_is_a_warning_not_an_error() -> None:
    ev = evaluate_line(valid_form(manager_value="4.500,00"))
    assert ev.valid and ev.view is not None
    assert len(ev.view.warnings) == 1
    assert ev.result is not None and ev.result.manager_line_total == D(4500)
