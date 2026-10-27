from decimal import Decimal as D

import pytest

from arcelikSalesHelper.domain.formatting import format_money_input
from arcelikSalesHelper.domain.money import parse_money
from arcelikSalesHelper.domain.result import Ok


@pytest.mark.parametrize(
    "value, expected",
    [
        ("5000", "5.000,00"),
        ("1234.5", "1.234,50"),
        ("0", "0,00"),
        ("1E+2", "100,00"),
        ("12.345", "12,345"),  # never rounded
        ("1234567.89", "1.234.567,89"),
        ("0.5", "0,50"),
        ("12.3450", "12,345"),
    ],
)
def test_format_money_input(value: str, expected: str) -> None:
    assert format_money_input(D(value)) == expected


@pytest.mark.parametrize(
    "value", ["0", "5000", "1234.5", "12.345", "999999999.99", "0.001"]
)
def test_input_text_always_parses_back_to_the_same_value(value: str) -> None:
    assert parse_money(format_money_input(D(value))) == Ok(D(value))


def test_format_money_input_rejects_non_finite() -> None:
    with pytest.raises(ValueError):
        format_money_input(D("NaN"))
