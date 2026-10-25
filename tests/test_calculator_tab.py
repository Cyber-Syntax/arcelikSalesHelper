from decimal import Decimal as D
from typing import Any

from PySide6.QtWidgets import QGroupBox, QLabel

from arcelikSalesHelper.application.calculator import TransactionEvaluation
from arcelikSalesHelper.domain.models import POS_LABEL
from arcelikSalesHelper.domain.products import ProductDraft
from arcelikSalesHelper.domain.result import Ok
from arcelikSalesHelper.ui.calculator_tab import CalculatorTab


def add_product(repo, name: str = "Fridge"):
    result = repo.add(ProductDraft(name, D(5000), D(4000), None))
    assert isinstance(result, Ok), result
    return result.value


def fill(
    row: Any,
    name: str,
    regular: str,
    website: str,
    quantity: int = 1,
    gift: str | None = None,
    manager: str | None = None,
) -> None:
    line = row.line
    line.name_edit.setText(name)
    line.regular_edit.setText(regular)
    line.website_edit.setText(website)
    line.quantity_spin.setValue(quantity)
    if gift is not None:
        line.gift_check.setChecked(True)
        line.gift_name_edit.setText(gift)
    if manager is not None:
        line.manager_edit.setText(manager)


def titles(tab: CalculatorTab) -> list[str]:
    return [box.title() for box in tab.panel.findChildren(QGroupBox)]


def test_multiple_lines_can_be_added_reordered_and_removed(
    qtbot, repo
) -> None:
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.add_line()
    fill(tab.rows[0], "Fridge", "5.000,00", "4.000,00", manager="3.000,00")
    fill(
        tab.rows[1],
        "Washer",
        "6.000,00",
        "5.000,00",
        quantity=3,
        gift="Vacuum",
        manager="4.500,00",
    )
    before = tab.evaluation.result
    assert before is not None
    tab.rows[1].up_button.click()
    assert tab.rows[0].line.name_edit.text() == "Washer"
    assert tab.evaluation.result is not None
    assert tab.evaluation.result.totals == before.totals
    tab.rows[0].remove_button.click()
    assert len(tab.rows) == 1


def test_invalid_line_keeps_valid_card_but_hides_totals(qtbot, repo) -> None:
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill(tab.rows[0], "Fridge", "5.000,00", "4.000,00", manager="3.000,00")
    tab.add_line()
    fill(tab.rows[1], "Washer", "6.000,00", "5.000,00")
    tab.rows[1].line.coupon_edit.setText("99.999,00")
    assert not tab.evaluation.valid
    assert "Line 1: Fridge" in titles(tab)
    assert "Transaction totals" not in titles(tab)
    assert any(
        "Lines to complete or fix" in label.text()
        for label in tab.panel.findChildren(QLabel)
    )


def test_product_refresh_updates_all_rows_without_overwriting_values(
    qtbot, repo
) -> None:
    product = add_product(repo)
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.add_line()
    for row in tab.rows:
        row.line.product_combo.setCurrentIndex(1)
    repo.archive(product.id)
    tab.refresh_products()
    assert all(row.line.product_combo.currentIndex() == 0 for row in tab.rows)
    assert all(row.line.regular_edit.text() == "5.000,00" for row in tab.rows)


def test_save_emits_transaction_evaluation(qtbot, repo) -> None:
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    fill(tab.rows[0], "Fridge", "5.000,00", "4.000,00")
    with qtbot.waitSignal(tab.save_requested) as blocker:
        tab.save_button.click()
    sent = blocker.args[0]
    assert isinstance(sent, TransactionEvaluation)
    assert sent.forms[0].product_name == "Fridge"
