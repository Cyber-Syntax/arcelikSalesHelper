from decimal import Decimal as D
from typing import Any

from PySide6.QtWidgets import QGroupBox, QLabel

from arcelikSalesHelper.application.calculator import TransactionEvaluation
from arcelikSalesHelper.domain.models import POS_LABEL
from arcelikSalesHelper.ui.calculator_tab import CalculatorTab

from .test_ui import add_product


def fill(
    row: Any,
    name: str,
    regular: str,
    website: str,
    qty: int = 1,
    gift: str | None = None,
    manager: str | None = None,
    total_mode: bool = False,
    coupon: str = "",
) -> None:
    line = row.line
    line.name_edit.setText(name)
    line.regular_edit.setText(regular)
    line.website_edit.setText(website)
    line.quantity_spin.setValue(qty)
    line.coupon_edit.setText(coupon)
    if gift is not None:
        line.gift_check.setChecked(True)
        line.gift_name_edit.setText(gift)
    if manager is not None:
        line.manager_edit.setText(manager)
    if total_mode:
        line.line_radio.setChecked(True)


def fill_two(tab: CalculatorTab) -> None:
    tab.add_line()
    fill(tab.rows[0], "Fridge", "5.000,00", "4.000,00", manager="3.000,00")
    fill(
        tab.rows[1],
        "Washer",
        "6.000,00",
        "5.000,00",
        qty=3,
        gift="Vacuum",
        manager="4.500,00",
    )


def titles(tab: CalculatorTab) -> list[str]:
    return [b.title() for b in tab.panel.findChildren(QGroupBox)]


def layout_order(tab: CalculatorTab) -> list[Any]:
    return [tab._rows_layout.itemAt(i).widget() for i in range(len(tab.rows))]


def pos_total(tab: CalculatorTab) -> D | None:
    assert tab.evaluation.result is not None
    return tab.evaluation.result.totals.pos.value


# ---- lines ----------------------------------------------------------------


def test_fresh_calculator_has_one_incomplete_line_and_no_save(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    assert len(tab.rows) == 1
    assert not tab.save_button.isEnabled()
    assert not tab.rows[0].remove_button.isEnabled()
    assert titles(tab) == ["Line 1"]
    assert all(b.error_text == "" for b in tab.rows[0].line.blocks.values())


def test_add_and_remove_lines_keep_at_least_one(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.add_button.click()
    assert len(tab.rows) == 2
    assert [r.title() for r in tab.rows] == ["Line 1", "Line 2"]
    assert tab.rows[0].remove_button.isEnabled()
    tab.rows[1].remove_button.click()
    assert len(tab.rows) == 1
    tab.remove_line(tab.rows[0])  # ignored: the last line stays
    assert len(tab.rows) == 1


def test_move_buttons_are_disabled_at_the_ends(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.add_line()
    assert (
        not tab.rows[0].up_button.isEnabled()
        and tab.rows[0].down_button.isEnabled()
    )
    assert (
        tab.rows[1].up_button.isEnabled()
        and not tab.rows[1].down_button.isEnabled()
    )


# ---- totals and independence ----------------------------------------------


def test_mixed_gift_and_no_gift_lines_give_the_expected_totals(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)
    assert tab.evaluation.valid and tab.save_button.isEnabled()
    result = tab.evaluation.result
    assert result is not None
    assert result.totals.regular.value == D(23000)
    assert result.totals.ten_pct.value == D(19800)
    assert pos_total(tab) == D(20500)
    assert not tab.rows[
        0
    ].line.gift_check.isChecked()  # gift state is per line
    assert tab.rows[1].line.gift_check.isChecked()


def test_removing_a_line_recomputes_totals(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)
    tab.rows[0].remove_button.click()
    assert len(tab.rows) == 1 and tab.rows[0].line.name_edit.text() == "Washer"
    assert pos_total(tab) == D(16500)


def test_reordering_moves_the_state_with_the_line(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)
    before = tab.evaluation.result
    assert before is not None

    tab.rows[1].up_button.click()
    assert layout_order(tab) == tab.rows
    first = tab.rows[0].line
    assert first.name_edit.text() == "Washer"
    assert first.quantity_spin.value() == 3
    assert (
        first.gift_check.isChecked()
        and first.gift_name_edit.text() == "Vacuum"
    )
    assert first.manager_edit.text() == "4.500,00"
    assert [r.title() for r in tab.rows] == ["Line 1", "Line 2"]
    after = tab.evaluation.result
    assert after is not None and after.totals == before.totals

    tab.rows[0].down_button.click()  # and back again
    assert tab.rows[0].line.name_edit.text() == "Fridge"


def test_invalid_line_hides_totals_but_keeps_the_valid_card(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)
    tab.rows[1].line.coupon_edit.setText(
        "99.999,00"
    )  # more than the website price
    assert not tab.evaluation.valid and not tab.save_button.isEnabled()
    assert tab.rows[1].line.blocks["coupon"].error_text != ""
    shown = titles(tab)
    assert "Line 1: Fridge" in shown and POS_LABEL in shown
    assert "Transaction totals" not in shown
    assert any(
        "Lines to complete or fix: 2" in lb.text()
        for lb in tab.panel.findChildren(QLabel)
    )

    tab.rows[1].line.coupon_edit.setText("")
    assert tab.evaluation.valid and "Transaction totals" in titles(tab)


# ---- comparison -----------------------------------------------------------


def test_options_are_side_by_side_only_for_lines_with_a_gift(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill(tab.rows[0], "Fridge", "5.000,00", "4.000,00")
    shown = titles(tab)
    assert (
        shown.count("Website discount option") == 1
        and "Gift option" not in shown
    )

    tab.add_line()
    fill(tab.rows[1], "Washer", "6.000,00", "5.000,00", gift="Vacuum")
    shown = titles(tab)
    assert (
        shown.count("Website discount option") == 2
        and shown.count("Gift option") == 1
    )


def test_panel_never_recommends_an_option(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)
    text = " ".join(lb.text() for lb in tab.panel.findChildren(QLabel)).lower()
    assert (
        "recommend" not in text and "best" not in text and "winner" not in text
    )


# ---- products and save ----------------------------------------------------


def test_selecting_a_saved_product_copies_values_and_never_writes_back(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    product = add_product(repo, gift="Vacuum")
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    line = tab.rows[0].line
    line.product_combo.setCurrentIndex(1)
    assert line.name_edit.text() == "Fridge" and line.name_edit.isReadOnly()
    assert (
        line.regular_edit.text() == "5.000,00"
        and line.gift_name_edit.text() == "Vacuum"
    )
    assert tab.evaluation.valid

    line.coupon_edit.setText("100")
    line.gift_name_edit.setText("Toaster")
    line.manager_edit.setText("3.000,00")
    assert repo.get(product.id) == product


def test_refresh_updates_every_row_and_keeps_entered_values(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    product = add_product(repo)
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.add_line()
    for row in tab.rows:
        row.line.product_combo.setCurrentIndex(1)
    assert all(r.line.selected_product() is not None for r in tab.rows)

    repo.archive(product.id)
    add_product(repo, "Washer")
    tab.refresh_products()
    for row in tab.rows:
        assert row.line.product_combo.count() == 2  # one-off + Washer
        assert row.line.product_combo.currentIndex() == 0
        assert row.line.regular_edit.text() == "5.000,00"
    assert tab.evaluation.valid


def test_ambiguous_price_shows_a_hint(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.rows[0].line.regular_edit.setText("5.000")
    assert "5.000,00 TL" in tab.rows[0].line.blocks["regular_price"].hint_text


def test_save_emits_the_transaction_evaluation_with_entered_text(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill_two(tab)
    with qtbot.waitSignal(tab.save_requested) as blocker:
        tab.save_button.click()
    sent = blocker.args[0]
    assert isinstance(sent, TransactionEvaluation) and sent.valid
    assert [f.product_name for f in sent.forms] == ["Fridge", "Washer"]
    assert sent.forms[1].manager_value == "4.500,00"
