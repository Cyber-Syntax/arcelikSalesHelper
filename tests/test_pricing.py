from decimal import Decimal, Decimal as D

import pytest

from arcelikSalesHelper.application.calculator import (
    LineForm,
    evaluate_with_reduction,
)
from arcelikSalesHelper.domain.models import (
    LineInput,
    ManagerMode,
    PosCalculationMode,
)
from arcelikSalesHelper.domain.pricing import (
    build_options,
    calculate_line,
    calculate_transaction,
    effective_website_price,
    manager_totals,
    pos_amount,
)
from arcelikSalesHelper.domain.result import Err, Ok


def make(**kw: object) -> LineInput:
    base: dict[str, object] = dict(
        product_name="Fridge",
        quantity=1,
        regular_price=D(5000),
        website_discounted_price=D(4000),
    )
    base.update(kw)
    return LineInput(**base)  # type: ignore[arg-type]


def calc(line: LineInput):
    result = calculate_line(line)
    assert isinstance(result, Ok), result
    return result.value


def test_real_world_examples_are_exact():
    first = calc(
        make(
            regular_price=D(145298),
            website_discounted_price=D(132798),
            manager_value=D(112000),
            manager_mode=ManagerMode.UNIT,
        )
    )
    assert first.ten_pct_base == D(132798)
    assert first.ten_pct_discount_unit == D("13279.80")
    assert first.ten_pct_unit == D("119518.20")
    assert first.pos_amount == D(124500)
    second = calc(
        make(
            regular_price=D(54299),
            website_discounted_price=D(48299),
            manager_value=D(43500),
            manager_mode=ManagerMode.UNIT,
        )
    )
    assert second.ten_pct_unit == D("43469.10")
    assert second.pos_amount == D(49500)


def test_gift_and_no_gift_ten_percent_bases():
    assert calc(make()).ten_pct_base == D(4000)
    gift = calc(make(gift_selected=True))
    assert gift.ten_pct_base == D(5000)
    assert gift.ten_pct_discount_unit == D(500)
    assert gift.ten_pct_unit == D(4500)


def test_zero_website_price_uses_regular_price_for_no_discount_line():
    line = make(
        regular_price=D(38299),
        website_discounted_price=D(0),
        manager_value=D(32000),
        manager_mode=ManagerMode.UNIT,
    )
    result = calc(line)
    assert effective_website_price(line) == D(38299)
    assert result.website_discounted_total == D(38299)
    assert result.discount_amount == D(0)
    assert result.pos_amount == D(32000)
    assert result.ten_pct_base == D(38299)
    assert result.ten_pct_unit == D("34469.10")


def test_zero_website_price_keeps_gift_scenario_on_regular_price():
    line = make(
        regular_price=D(38299),
        website_discounted_price=D(0),
        gift_selected=True,
    )
    result = calc(line)
    website, gift = build_options(line, result)
    assert result.ten_pct_base == D(38299)
    assert website.ten_pct_base == D(38299)
    assert gift is not None and gift.ten_pct_base == D(38299)
    assert result.discount_amount == D(0)


def test_manager_unit_and_authoritative_line_modes_with_quantity():
    assert manager_totals(D(4500), ManagerMode.UNIT, 3) == (D(4500), D(13500))
    line = calc(
        make(quantity=3, manager_value=D(10), manager_mode=ManagerMode.LINE)
    )
    assert line.manager_line_total == D(10)
    assert str(line.manager_unit).startswith(
        "3.333333"
    ) and line.manager_unit != D("3.33")
    assert line.pos_amount == D(3010)


def test_pos_uses_normal_website_discounted_total():
    assert pos_amount(D(145298), D(132798), D(112000)) == D(124500)


def test_percentage_pos_mode_grosses_up_manager_price_and_rounds_pos():
    line = calc(
        make(
            regular_price=D(38299),
            website_discounted_price=D("34469.1"),
            manager_value=D(30000),
            manager_mode=ManagerMode.UNIT,
            pos_calculation_mode=PosCalculationMode.PERCENTAGE,
        )
    )
    assert line.pos_calculation_mode is PosCalculationMode.PERCENTAGE
    assert line.pos_discount_percentage == D("10.0")
    assert line.pos_amount == D("33333.33")
    assert line.manager_line_total == D(30000)


def test_percentage_pos_mode_respects_line_total_quantity_and_gift_pos():
    line = calc(
        make(
            quantity=2,
            regular_price=D(100),
            website_discounted_price=D(90),
            manager_value=D(300),
            manager_mode=ManagerMode.LINE,
            pos_calculation_mode=PosCalculationMode.PERCENTAGE,
        )
    )
    assert line.pos_amount == D("333.33")
    gift = calc(
        make(
            regular_price=D(100),
            website_discounted_price=D(90),
            gift_selected=True,
            manager_value=D(30),
            manager_mode=ManagerMode.UNIT,
            pos_calculation_mode=PosCalculationMode.PERCENTAGE,
        )
    )
    assert gift.pos_amount == D(30)


def test_options_keep_manager_value_on_selected_option_only():
    line = make(
        gift_selected=True,
        gift_name="TKM 9961",
        manager_value=D(48000),
        manager_mode=ManagerMode.UNIT,
    )
    website, gift = build_options(line, calc(line))
    assert website.manager_line_total is None
    assert gift is not None and gift.manager_line_total == D(48000)
    assert website.ten_pct_base == D(4000)


def test_quantity_scales_totals_and_transaction():
    line = make(
        quantity=3, manager_value=D(4500), manager_mode=ManagerMode.UNIT
    )
    result = calc(line)
    assert result.regular_total == D(15000)
    assert result.website_discounted_total == D(12000)
    assert result.pos_amount == D(16500)
    transaction = calculate_transaction([line])
    assert isinstance(transaction, Ok)
    assert transaction.value.totals.website_discounted.value == D(12000)


@pytest.mark.parametrize(
    "line",
    [
        make(quantity=0),
        make(quantity=True),
        make(regular_price=D(-1)),
        make(regular_price=D("NaN")),
        make(website_discounted_price=D(-1)),
        make(website_discounted_price=D("Infinity")),
        make(manager_value=D(1)),
        make(manager_value=D(-1), manager_mode=ManagerMode.UNIT),
        make(manager_value=D("NaN"), manager_mode=ManagerMode.LINE),
        make(manager_mode=ManagerMode.UNIT),
    ],
)
def test_invalid_calculator_values_are_rejected(line: LineInput):
    assert isinstance(calculate_line(line), Err)


def test_manager_total_above_website_total_is_a_warning_and_is_preserved():
    line = make(
        quantity=2,
        website_discounted_price=D(4000),
        manager_value=D(9000),
        manager_mode=ManagerMode.LINE,
    )
    result = calc(line)
    assert result.manager_line_total == D(9000)
    assert len(result.warnings) == 1
    assert result.warnings[0].code == "manager_exceeds_website"


def test_transaction_totals_mark_missing_manager_lines_without_partial_sum():
    lines = [
        make(manager_value=D(1000), manager_mode=ManagerMode.UNIT),
        make(product_name="Washer"),
    ]
    result = calculate_transaction(lines)
    assert isinstance(result, Ok)
    assert result.value.totals.manager.value is None
    assert result.value.totals.manager.missing_lines == (1,)
    assert result.value.totals.regular.value == D(10000)


def test_three_percent_lines_target_81000():
    forms = [
        LineForm(
            "OCD", regular_price="33999", website_discounted_price="30599,1"
        ),
        LineForm(
            "ADE", regular_price="32499", website_discounted_price="29249,1"
        ),
        LineForm(
            "AFC", regular_price="34499", website_discounted_price="31049,1"
        ),
    ]
    ev = evaluate_with_reduction(forms, "", "81000")
    assert ev.result.totals.pos.value == Decimal("90000.00")


def test_three_percent_lines_shown_and_target():
    forms = [
        LineForm(
            "OCD", regular_price="33999", website_discounted_price="30599,1"
        ),
        LineForm(
            "ADE", regular_price="32499", website_discounted_price="29249,1"
        ),
        LineForm(
            "AFC", regular_price="34499", website_discounted_price="31049,1"
        ),
    ]
    ev = evaluate_with_reduction(forms, "90897,3", "81000")
    assert ev.result.totals.pos.value == Decimal("90000.00")


def test_catalog_website_prices_use_pos_shown_total_rate():
    """The online price can differ from the POS campaign; trust the shown net."""
    forms = [
        LineForm(
            "OCD K 752 EWS",
            regular_price="33999",
            website_discounted_price="31499",
        ),
        LineForm(
            "ADE 9062 S1",
            regular_price="32499",
            website_discounted_price="30499",
        ),
        LineForm(
            "AFC 341 S",
            regular_price="34499",
            website_discounted_price="31499",
        ),
    ]
    ev = evaluate_with_reduction(forms, "90897,3", "81000")

    assert ev.valid
    assert ev.result.totals.pos.value == Decimal("90000.00")
    assert ev.result.totals.manager.value == Decimal("81000")
    assert [line.pos_amount for line in ev.result.lines] == [
        Decimal("30297.04"),
        Decimal("28960.36"),
        Decimal("30742.60"),
    ]


def test_mixed_percentage_and_fixed_lines_keep_per_line_model():
    forms = [
        LineForm(
            "OCD K 752 EWS",
            regular_price="33999",
            website_discounted_price="30599,1",
        ),
        LineForm(
            "ADE 9062 S1",
            regular_price="32499",
            website_discounted_price="29249,1",
        ),
        LineForm(
            "AFC 341 S",
            regular_price="34499",
            website_discounted_price="31049,1",
        ),
        LineForm(
            "901 KMP I",
            regular_price="56299",
            website_discounted_price="46299",
        ),
    ]
    ev = evaluate_with_reduction(forms, "137196,3", "123000")

    assert ev.valid
    assert ev.result.totals.pos.value == Decimal("143099.70")
    assert [line.pos_amount for line in ev.result.lines] == [
        Decimal("33999"),
        Decimal("32499"),
        Decimal("34499"),
        Decimal("42102.70"),
    ]
