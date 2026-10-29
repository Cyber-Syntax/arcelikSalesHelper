from decimal import Decimal

import pytest

from arcelikSalesHelper.domain.formatting import (
    format_decimal_exact,
    format_try,
)
from arcelikSalesHelper.domain.money import parse_money, parse_money_ex
from arcelikSalesHelper.domain.result import Err, Ok


@pytest.mark.parametrize(
    "text, expected",
    [
        ("54.999,00", "54999"),  # acceptance #4: three formats
        ("54999", "54999"),
        ("54999.00", "54999"),
        ("54.999", "54999"),
        ("1.234.567,89", "1234567.89"),
        ("1,234.56", "1234.56"),  # last separator is the decimal mark
        ("1.234,56", "1234.56"),
        ("1.234.567", "1234567"),
        ("1234,567", "1234.567"),
        ("12.5", "12.5"),
        ("12,5", "12.5"),
        ("0,5", "0.5"),
        ("0.5", "0.5"),
        ("0.500", "0.5"),  # leading zero group cannot be a thousands group
        ("1234.567", "1234.567"),
        ("0", "0"),
        ("0,00", "0"),
        ("  54.999,00 TL ", "54999"),
        ("54999 try", "54999"),
        (" 1.234,56 TRY ", "1234.56"),
        ("12TL", "12"),
    ],
)
def test_accepts(text: str, expected: str) -> None:
    assert parse_money(text) == Ok(Decimal(expected))


@pytest.mark.parametrize(
    "text",
    [
        "", "   ", "TL", "-5", "- 5 TL", "+5", "abc", "NaN", "Infinity", "1e5", "1E+3",
        "1.23.456", "1.234.56", "12..5", "1,2,3", "1.234,56,7", "1.2345,6",
        "5,", ",5", ".5", "54999.", ".", ",", "1 234", "１２", "5" * 41,
    ],
)  # fmt: skip
def test_rejects(text: str) -> None:
    assert isinstance(parse_money(text), Err)


def test_dot_followed_by_three_digits_is_read_as_thousands_and_flagged_ambiguous() -> (
    None
):
    # "1.234" could be 1234 or 1.234; we choose thousands (Turkish convention).
    parsed = parse_money_ex("1.234")
    assert isinstance(parsed, Ok)
    assert parsed.value.value == Decimal("1234")
    assert parsed.value.ambiguous is True


@pytest.mark.parametrize(
    "text", ["1.234.567", "54999.00", "54.999,00", "54999", "12,5"]
)
def test_unambiguous_inputs_are_not_flagged(text: str) -> None:
    parsed = parse_money_ex(text)
    assert isinstance(parsed, Ok)
    assert parsed.value.ambiguous is False


@pytest.mark.parametrize(
    "value, expected",
    [
        ("54999", "54.999,00 TL"),
        ("153345.56", "153.345,56 TL"),
        ("0.01", "0,01 TL"),
        ("0", "0,00 TL"),
        ("0.005", "0,005 TL"),
        ("0.004", "0,004 TL"),
        ("2.675", "2,675 TL"),
        ("999.995", "999,995 TL"),
        ("1234567.891", "1.234.567,891 TL"),
        ("-1234.5", "-1.234,50 TL"),
        ("-0.001", "-0,001 TL"),
        (
            "3.3333333333333333333333333333333333",
            "3,3333333333333333333333333333333333 TL",
        ),
        (
            "123456789012345678901234567890.12",
            "123.456.789.012.345.678.901.234.567.890,12 TL",
        ),
    ],
)
def test_format_try(value: str, expected: str) -> None:
    assert format_try(Decimal(value)) == expected


def test_format_try_rejects_non_finite() -> None:
    with pytest.raises(ValueError):
        format_try(Decimal("NaN"))


def test_format_decimal_exact_is_plain_and_lossless() -> None:
    assert format_decimal_exact(Decimal("1E+2")) == "100"
    assert format_decimal_exact(Decimal("0.10")) == "0.10"
    third = Decimal(10) / Decimal(3)
    assert Decimal(format_decimal_exact(third)) == third


def test_roundtrip_deterministic() -> None:
    for text in [
        "0.00",
        "0.01",
        "999.99",
        "1000.00",
        "54999.00",
        "153345.56",
        "1234567.89",
        "0.005",
        "999.995",
    ]:
        d = Decimal(text)
        assert parse_money(format_try(d)) == Ok(d)


def test_format_try_keeps_fractional_digits_at_carry_boundary() -> None:
    assert format_try(Decimal("999.999")) == "999,999 TL"
    assert format_try(Decimal("999.995")) != "1.000,00 TL"


def test_roundtrip_hypothesis() -> None:
    pytest.importorskip("hypothesis")
    from hypothesis import given
    from hypothesis import strategies as st

    @given(st.decimals(min_value=0, max_value=Decimal("1e12"), places=2))
    def check(d: Decimal) -> None:
        assert parse_money(format_try(d)) == Ok(d)

    check()
