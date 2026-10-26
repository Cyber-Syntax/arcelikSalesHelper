from decimal import Decimal as D

import pytest

from arcelikSalesHelper.domain.models import LineInput, ManagerMode
from arcelikSalesHelper.domain.pricing import build_options, calculate_line, calculate_transaction, manager_totals, pos_amount, ten_percent
from arcelikSalesHelper.domain.result import Err, Ok


def make(**kw: object) -> LineInput:
    base: dict[str, object] = dict(product_name="Fridge", quantity=1, regular_price=D(5000), website_discounted_price=D(4000))
    base.update(kw)
    return LineInput(**base)  # type: ignore[arg-type]


def calc(line: LineInput):
    result = calculate_line(line)
    assert isinstance(result, Ok), result
    return result.value


def test_real_world_examples_are_exact():
    first = calc(make(regular_price=D("145298"), website_discounted_price=D("132798"), manager_value=D("112000"), manager_mode=ManagerMode.UNIT))
    assert first.ten_pct_base == D("132798")
    assert first.ten_pct_discount_unit == D("13279.80")
    assert first.ten_pct_unit == D("119518.20")
    assert first.pos_amount == D("124500")
    second = calc(make(regular_price=D("54299"), website_discounted_price=D("48299"), manager_value=D("43500"), manager_mode=ManagerMode.UNIT))
    assert second.ten_pct_unit == D("43469.10")
    assert second.pos_amount == D("49500")


def test_gift_and_no_gift_ten_percent_bases():
    assert calc(make()).ten_pct_base == D("4000")
    gift = calc(make(gift_selected=True))
    assert gift.ten_pct_base == D("5000")
    assert gift.ten_pct_discount_unit == D("500")
    assert gift.ten_pct_unit == D("4500")


def test_manager_unit_and_authoritative_line_modes_with_quantity():
    assert manager_totals(D(4500), ManagerMode.UNIT, 3) == (D(4500), D(13500))
    line = calc(make(quantity=3, manager_value=D(10), manager_mode=ManagerMode.LINE))
    assert line.manager_line_total == D(10)
    assert str(line.manager_unit).startswith("3.333333") and line.manager_unit != D("3.33")
    assert line.pos_amount == D(3010)


def test_pos_uses_normal_website_discounted_total():
    assert pos_amount(D(145298), D(132798), D(112000)) == D(124500)


def test_options_keep_manager_value_on_selected_option_only():
    line = make(gift_selected=True, gift_name="TKM 9961", manager_value=D(48000), manager_mode=ManagerMode.UNIT)
    website, gift = build_options(line, calc(line))
    assert website.manager_line_total is None
    assert gift is not None and gift.manager_line_total == D(48000)
    assert website.ten_pct_base == D(4000)


def test_quantity_scales_totals_and_transaction():
    line = make(quantity=3, manager_value=D(4500), manager_mode=ManagerMode.UNIT)
    result = calc(line)
    assert result.regular_total == D(15000)
    assert result.website_discounted_total == D(12000)
    assert result.pos_amount == D(16500)
    transaction = calculate_transaction([line])
    assert isinstance(transaction, Ok)
    assert transaction.value.totals.website_discounted.value == D(12000)


@pytest.mark.parametrize("line", [make(quantity=0), make(regular_price=D(-1)), make(website_discounted_price=D(-1)), make(manager_value=D(1))])
def test_invalid_calculator_values_are_rejected(line: LineInput):
    assert isinstance(calculate_line(line), Err)
