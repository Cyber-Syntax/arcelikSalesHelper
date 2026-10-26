from decimal import Decimal as D

from arcelikSalesHelper.application.calculator import LineForm, evaluate_line
from arcelikSalesHelper.domain.models import POS_LABEL, ManagerMode


def form(**kw: object) -> LineForm:
    values: dict[str, object] = dict(product_name="Fridge", regular_price="145.298,00", website_discounted_price="132.798,00")
    values.update(kw)
    return LineForm(**values)  # type: ignore[arg-type]


def test_standard_calculation_and_pos_use_website_discounted_price():
    ev = evaluate_line(form(manager_value="112.000,00"))
    assert ev.valid and ev.result is not None and ev.line is not None
    assert ev.result.ten_pct_base == D("132798")
    assert ev.result.ten_pct_unit == D("119518.20")
    assert ev.result.pos_amount == D("124500")
    assert POS_LABEL in [section.title for section in ev.view.sections]


def test_gift_uses_regular_price_for_ten_percent():
    ev = evaluate_line(form(gift_selected=True, gift_name="TKM 9961"))
    assert ev.result is not None
    assert ev.result.ten_pct_base == D("145298")
    assert ev.result.ten_pct_unit == D("130768.20")


def test_total_line_manager_value_remains_authoritative():
    ev = evaluate_line(form(quantity=3, manager_value="10", manager_mode=ManagerMode.LINE))
    assert ev.result is not None
    assert ev.result.manager_line_total == D(10)
    assert str(ev.result.manager_unit).startswith("3.333333") and ev.result.manager_unit != D("3.33")


def test_invalid_price_hides_results():
    ev = evaluate_line(form(website_discounted_price="bad"))
    assert not ev.valid and ev.result is None and ev.view is None
    assert {error.field for error in ev.errors} == {"website_discounted_price"}


def test_coupon_is_not_an_input_or_result():
    assert "coupon" not in LineForm.__dataclass_fields__
    ev = evaluate_line(form())
    assert ev.view is not None
    assert all("kupon" not in row.label.casefold() for section in ev.view.sections for row in section.rows)
