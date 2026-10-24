from decimal import Decimal as D

import pytest

from arcelikSalesHelper.domain.models import LineInput, ManagerMode
from arcelikSalesHelper.domain.pricing import (
    build_options,
    calculate_line,
    effective_website_unit,
    manager_totals,
    pos_amount,
    ten_percent,
)
from arcelikSalesHelper.domain.result import Err, Ok


def make(**kw: object) -> LineInput:
    base: dict[str, object] = dict(
        product_name="Fridge",
        quantity=1,
        regular_price=D(5000),
        website_price=D(4000),
    )
    base.update(kw)
    return LineInput(**base)  # type: ignore[arg-type]


def calc(line: LineInput):
    r = calculate_line(line)
    assert isinstance(r, Ok), r
    return r.value


def test_coupon_reduces_website_price() -> None:  # acceptance #5
    assert effective_website_unit(D(4000), D(50)) == D(3950)
    assert calc(make(coupon=D(50))).effective_website_unit == D(3950)


def test_ten_percent_helper() -> None:
    assert ten_percent(D(3950)) == (D(395), D(3555))


def test_no_gift_ten_percent_uses_effective_website_price() -> (
    None
):  # acceptance #6
    r = calc(make(coupon=D(50)))
    assert r.ten_pct_base == D(3950)
    assert r.ten_pct_discount_unit == D(395)
    assert r.ten_pct_unit == D(3555)
    assert r.ten_pct_total == D(3555)


def test_gift_ten_percent_uses_regular_price() -> None:  # acceptance #7
    r = calc(make(coupon=D(50), gift_selected=True, gift_name="Vacuum"))
    assert r.ten_pct_base == D(5000)
    assert r.ten_pct_discount_unit == D(500)
    assert r.ten_pct_unit == D(4500)


def test_quantity_scales_every_total() -> None:
    r = calc(make(quantity=3, coupon=D(50)))
    assert r.regular_total == D(15000)
    assert r.website_total == D(12000)
    assert r.coupon_total == D(150)
    assert r.effective_website_total == D(11850)
    assert r.ten_pct_unit == D(3555)
    assert r.ten_pct_total == D(10665)


def test_manager_unit_mode() -> None:
    assert manager_totals(D(4500), ManagerMode.UNIT, 3) == (D(4500), D(13500))
    r = calc(
        make(quantity=3, manager_value=D(4500), manager_mode=ManagerMode.UNIT)
    )
    assert r.manager_line_total == D(13500)
    assert r.manager_unit == D(4500)
    assert r.manager_mode is ManagerMode.UNIT


def test_manager_line_mode() -> None:
    assert manager_totals(D(12000), ManagerMode.LINE, 3) == (D(4000), D(12000))
    r = calc(
        make(quantity=3, manager_value=D(12000), manager_mode=ManagerMode.LINE)
    )
    assert r.manager_line_total == D(12000)
    assert r.manager_unit == D(4000)


def test_manager_value_is_not_a_percentage_or_compounded_with_ten_percent() -> (
    None
):
    r = calc(make(manager_value=D(3000), manager_mode=ManagerMode.UNIT))
    assert r.manager_line_total == D(3000)
    assert r.ten_pct_total == D(3600)  # independent of the manager value


def test_pos_acceptance_example() -> None:  # acceptance #12
    assert pos_amount(D(5000), D(4000), D(3000)) == D(4000)
    r = calc(make(manager_value=D(3000), manager_mode=ManagerMode.UNIT))
    assert r.pos_amount == D(4000)


def test_pos_ignores_coupon() -> None:
    no_coupon = calc(
        make(manager_value=D(3000), manager_mode=ManagerMode.UNIT)
    )
    coupon = calc(
        make(
            coupon=D(500), manager_value=D(3000), manager_mode=ManagerMode.UNIT
        )
    )
    assert coupon.pos_amount == no_coupon.pos_amount == D(4000)


def test_pos_with_quantity_and_gift() -> None:
    r = calc(
        make(
            quantity=3, regular_price=D(6000), website_price=D(5000),
            gift_selected=True, manager_value=D(4500), manager_mode=ManagerMode.UNIT,
        )
    )  # fmt: skip
    assert r.pos_amount == D(16500)  # (18000 - 15000) + 13500


def test_line_total_is_exact_even_when_unit_is_not_terminating() -> None:
    r = calc(
        make(
            quantity=3, regular_price=D(100), website_price=D(90),
            manager_value=D(10), manager_mode=ManagerMode.LINE,
        )
    )  # fmt: skip
    assert r.manager_line_total == D(10)
    assert r.manager_unit != D(
        "3.33"
    )  # derived value, not rounded in the domain
    assert r.pos_amount == D(
        40
    )  # (300 - 270) + 10, unaffected by the unit value


def test_no_manager_value_means_no_manager_or_pos_result() -> None:
    r = calc(make())
    assert r.manager_line_total is None
    assert r.manager_unit is None
    assert r.pos_amount is None
    assert r.manager_mode is None


# ---- validation -----------------------------------------------------------


def codes(line: LineInput) -> set[str]:
    r = calculate_line(line)
    assert isinstance(r, Err)
    return {e.code for e in r.error}


def test_coupon_cannot_exceed_website_price() -> None:
    assert codes(make(coupon=D(4001))) == {"coupon_exceeds_website"}


def test_coupon_equal_to_website_price_is_allowed() -> None:
    assert calc(make(coupon=D(4000))).effective_website_unit == D(0)


@pytest.mark.parametrize("qty", [0, -1])
def test_quantity_must_be_positive(qty: int) -> None:
    assert codes(make(quantity=qty)) == {"quantity_invalid"}


def test_quantity_rejects_bool() -> None:
    assert codes(make(quantity=True)) == {"quantity_invalid"}


def test_negative_prices_rejected() -> None:
    assert codes(make(regular_price=D(-1), website_price=D(-1))) == {
        "regular_price_invalid",
        "website_price_invalid",
    }


def test_negative_coupon_rejected() -> None:
    assert codes(make(coupon=D(-1))) == {"coupon_negative"}


def test_nan_rejected() -> None:
    assert "regular_price_invalid" in codes(make(regular_price=D("NaN")))


def test_manager_mode_required_with_value() -> None:
    assert codes(make(manager_value=D(10))) == {"manager_mode_required"}


def test_manager_mode_without_value_rejected() -> None:
    assert codes(make(manager_mode=ManagerMode.UNIT)) == {
        "manager_mode_without_value"
    }


def test_negative_manager_value_rejected() -> None:
    assert codes(make(manager_value=D(-1), manager_mode=ManagerMode.UNIT)) == {
        "manager_value_invalid"
    }


# ---- soft warnings --------------------------------------------------------


def test_no_gift_warns_against_effective_website_total_and_keeps_value() -> (
    None
):
    r = calc(
        make(
            coupon=D(500), manager_value=D(3600), manager_mode=ManagerMode.LINE
        )
    )
    assert [w.code for w in r.warnings] == ["manager_exceeds_website"]
    assert r.manager_line_total == D(3600)  # never altered


def test_gift_warns_against_normal_website_total() -> None:
    ok = calc(
        make(coupon=D(500), gift_selected=True, manager_value=D(3800),
             manager_mode=ManagerMode.UNIT)
    )  # fmt: skip
    assert ok.warnings == ()  # 3800 > effective (3500) but <= website (4000)
    high = calc(
        make(
            gift_selected=True,
            manager_value=D(4100),
            manager_mode=ManagerMode.UNIT,
        )
    )
    assert [w.code for w in high.warnings] == ["manager_exceeds_website"]


# ---- options --------------------------------------------------------------


def test_no_gift_no_name_has_no_gift_option() -> None:
    line = make()
    site, gift = build_options(line, calc(line))
    assert gift is None
    assert site.ten_pct_base == D(4000)


def test_gift_option_uses_regular_price_and_website_option_uses_effective() -> (
    None
):
    line = make(
        coupon=D(50), quantity=2, gift_selected=True, gift_name="  Vacuum ",
        manager_value=D(4500), manager_mode=ManagerMode.UNIT,
    )  # fmt: skip
    site, gift = build_options(line, calc(line))
    assert gift is not None
    assert gift.gift_name == "Vacuum"
    assert gift.ten_pct_base == D(5000)
    assert gift.ten_pct_unit == D(4500)
    assert gift.ten_pct_total == D(9000)
    assert gift.manager_line_total == D(9000)
    assert site.ten_pct_base == D(3950)
    assert site.ten_pct_total == D(7110)
    assert (
        site.manager_line_total is None
    )  # manager value is not assigned to both


def test_named_but_unselected_gift_is_shown_without_manager_value() -> None:
    line = make(
        gift_name="Vacuum",
        manager_value=D(3000),
        manager_mode=ManagerMode.UNIT,
    )
    site, gift = build_options(line, calc(line))
    assert gift is not None
    assert gift.manager_line_total is None
    assert site.manager_line_total == D(3000)
