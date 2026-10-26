from decimal import Decimal as D

from arcelikSalesHelper.application.calculator import LineForm, evaluate_line
from arcelikSalesHelper import strings as T
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


def test_zero_website_price_displays_regular_price_and_zero_discount():
    ev = evaluate_line(
        form(
            regular_price="38.299,00",
            website_discounted_price="0,00",
            manager_value="32.000,00",
        )
    )
    assert ev.result is not None and ev.view is not None
    assert ev.result.website_discounted_total == D("38299")
    assert ev.result.discount_amount == D("0")
    assert ev.result.pos_amount == D("32000")
    assert ev.result.ten_pct_unit == D("34469.10")
    prices = {row.label: row.value for row in ev.view.card.prices.rows}
    assert prices[T.LBL_WEBSITE_UNIT] == T.NO_WEBSITE_DISCOUNT
    assert prices[T.LBL_WEBSITE_DISCOUNTED_TOTAL] == T.NO_WEBSITE_DISCOUNT
    options = {row.label: row.value for row in ev.view.card.website_option.rows}
    assert options[T.LBL_WEBSITE_DISCOUNTED_TOTAL] == T.NO_WEBSITE_DISCOUNT
    assert options[T.LBL_WEBSITE_OFFER_TOTAL] == "34.469,10 TL"


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
