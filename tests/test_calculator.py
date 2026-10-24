from decimal import Decimal as D

from arcelikSalesHelper.domain.models import LineInput, ManagerMode
from arcelikSalesHelper.domain.pricing import calculate_transaction
from arcelikSalesHelper.domain.result import Err, Ok


def two_lines() -> list[LineInput]:
    return [
        LineInput("Fridge", 1, D(5000), D(4000),
                  manager_value=D(3000), manager_mode=ManagerMode.UNIT),
        LineInput("Washer", 3, D(6000), D(5000), gift_selected=True, gift_name="Vacuum",
                  manager_value=D(4500), manager_mode=ManagerMode.UNIT),
    ]  # fmt: skip


def test_mixed_gift_and_no_gift_totals() -> None:
    r = calculate_transaction(two_lines())
    assert isinstance(r, Ok)
    t = r.value.totals
    assert t.regular.value == D(23000)  # 5000 + 18000
    assert t.website.value == D(19000)  # 4000 + 15000
    assert t.effective_website.value == D(19000)
    assert t.ten_pct.value == D(19800)  # 3600 + (5400 * 3)
    assert t.manager.value == D(16500)  # 3000 + 13500
    assert t.pos.value == D(20500)  # 4000 + 16500
    assert r.value.lines[0].ten_pct_base == D(
        4000
    )  # no gift -> effective website
    assert r.value.lines[1].ten_pct_base == D(6000)  # gift -> regular


def test_line_state_is_independent() -> None:
    r = calculate_transaction(two_lines())
    assert isinstance(r, Ok)
    assert r.value.lines[0].manager_mode is ManagerMode.UNIT
    assert r.value.lines[1].quantity == 3


def test_missing_manager_value_yields_na_with_line_indices() -> None:
    lines = two_lines()
    lines.append(LineInput("Dryer", 1, D(2000), D(1500)))
    r = calculate_transaction(lines)
    assert isinstance(r, Ok)
    t = r.value.totals
    assert t.regular.value == D(25000)
    assert t.manager.value is None and t.manager.missing_lines == (2,)
    assert t.pos.value is None and t.pos.missing_lines == (2,)


def test_removing_a_line_recomputes_totals() -> None:
    lines = two_lines()[:1]
    r = calculate_transaction(lines)
    assert isinstance(r, Ok)
    assert r.value.totals.pos.value == D(4000)


def test_reordering_does_not_change_totals_or_per_line_results() -> None:
    a = calculate_transaction(two_lines())
    b = calculate_transaction(list(reversed(two_lines())))
    assert isinstance(a, Ok) and isinstance(b, Ok)
    assert a.value.totals == b.value.totals
    assert a.value.lines[0] == b.value.lines[1]


def test_errors_carry_line_index() -> None:
    lines = two_lines()
    lines.append(LineInput("Bad", 0, D(1), D(1)))
    r = calculate_transaction(lines)
    assert isinstance(r, Err)
    assert [(e.code, e.line_index) for e in r.error] == [
        ("quantity_invalid", 2)
    ]


def test_empty_transaction_is_an_error_not_a_zero_total() -> None:
    r = calculate_transaction([])
    assert isinstance(r, Err)
    assert r.error[0].code == "no_lines"


def test_warnings_are_collected_per_line() -> None:
    lines = [
        LineInput("A", 1, D(5000), D(4000), manager_value=D(4500),
                  manager_mode=ManagerMode.UNIT),
        LineInput("B", 1, D(5000), D(4000)),
    ]  # fmt: skip
    r = calculate_transaction(lines)
    assert isinstance(r, Ok)
    assert [w.line_index for ln in r.value.lines for w in ln.warnings] == [0]
