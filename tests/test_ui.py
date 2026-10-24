from decimal import Decimal as D
from typing import Any

from PySide6.QtWidgets import QGroupBox

from arcelikSalesHelper.domain.models import POS_LABEL
from arcelikSalesHelper.domain.products import ProductDraft
from arcelikSalesHelper.domain.result import Ok
from arcelikSalesHelper.infrastructure.repositories import ProductRepository
from arcelikSalesHelper.ui.calculator_tab import CalculatorTab
from arcelikSalesHelper.ui.products_tab import ProductDialog, ProductsTab


def add_product(
    repo: ProductRepository,
    name: str = "Fridge",
    regular: str = "5000",
    website: str = "4000",
    gift: str | None = None,
) -> Any:
    result = repo.add(ProductDraft(name, D(regular), D(website), gift))
    assert isinstance(result, Ok), result
    return result.value


# ---- calculator -----------------------------------------------------------


def test_fresh_calculator_is_incomplete_without_red_errors(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    assert tab.panel.content.isHidden()
    assert not tab.save_button.isEnabled()
    assert all(b.error_text == "" for b in tab.line.blocks.values())


def test_one_off_calculation_renders_results_and_pos_label(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    line = tab.line
    line.name_edit.setText("Fridge")
    line.regular_edit.setText("5.000,00")
    line.website_edit.setText("4.000,00")
    line.coupon_edit.setText("50")
    line.manager_edit.setText("3.000,00")

    assert tab.evaluation.valid
    assert tab.evaluation.result.pos_amount == D(4000)
    assert not tab.panel.content.isHidden()
    assert tab.save_button.isEnabled()
    titles = [b.title() for b in tab.panel.content.findChildren(QGroupBox)]
    assert POS_LABEL in titles


def test_invalid_input_hides_results_and_disables_save(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    line = tab.line
    line.name_edit.setText("Fridge")
    line.regular_edit.setText("5.000,00")
    line.website_edit.setText("4.000,00")
    assert not tab.panel.content.isHidden()

    line.coupon_edit.setText("9.000,00")  # more than the website price
    assert tab.panel.content.isHidden()  # no stale results
    assert not tab.save_button.isEnabled()
    assert line.blocks["coupon"].error_text != ""

    line.coupon_edit.setText("50")
    assert not tab.panel.content.isHidden()
    assert line.blocks["coupon"].error_text == ""


def test_ambiguous_price_shows_a_hint(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.line.regular_edit.setText("5.000")
    assert "5.000,00 TL" in tab.line.blocks["regular_price"].hint_text


def test_selecting_a_saved_product_copies_values_and_never_writes_back(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    product = add_product(repo, gift="Vacuum")
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.line.product_combo.setCurrentIndex(1)

    assert (
        tab.line.name_edit.text() == "Fridge"
        and tab.line.name_edit.isReadOnly()
    )
    assert tab.line.regular_edit.text() == "5.000,00"
    assert tab.line.website_edit.text() == "4.000,00"
    assert tab.line.gift_name_edit.text() == "Vacuum"
    assert tab.evaluation.valid

    tab.line.coupon_edit.setText("100")
    tab.line.gift_name_edit.setText("Toaster")
    tab.line.manager_edit.setText("3.000,00")
    assert repo.get(product.id) == product  # untouched


def test_refresh_keeps_selection_and_values_when_product_is_archived(
    qtbot, repo
) -> None:  # type: ignore[no-untyped-def]
    product = add_product(repo)
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.line.product_combo.setCurrentIndex(1)
    assert tab.line.selected_product() is not None

    repo.archive(product.id)
    tab.refresh_products()
    assert tab.line.product_combo.currentIndex() == 0  # back to one-off
    assert tab.line.regular_edit.text() == "5.000,00"  # values kept
    assert not tab.line.name_edit.isReadOnly()
    assert tab.evaluation.valid


def test_refresh_picks_up_newly_added_products(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    assert tab.line.product_combo.count() == 1
    add_product(repo)
    tab.refresh_products()
    assert tab.line.product_combo.count() == 2


def test_save_button_emits_the_current_evaluation(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    tab = CalculatorTab(repo)
    qtbot.addWidget(tab)
    tab.line.name_edit.setText("Fridge")
    tab.line.regular_edit.setText("5000")
    tab.line.website_edit.setText("4000")
    with qtbot.waitSignal(tab.save_requested) as blocker:
        tab.save_button.click()
    assert blocker.args[0].valid


# ---- products -------------------------------------------------------------


def test_dialog_adds_a_product(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    dialog = ProductDialog(repo)
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("Washer")
    dialog.regular_edit.setText("6.000,00")
    dialog.website_edit.setText("5.500")
    assert "5.500,00 TL" in dialog.blocks["website_price"].hint_text
    dialog.accept()
    assert dialog.saved is not None
    assert dialog.saved.website_price == D(5500)
    assert [p.name for p in repo.search()] == ["Washer"]


def test_dialog_shows_inline_errors_and_stays_open(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    dialog = ProductDialog(repo)
    qtbot.addWidget(dialog)
    dialog.regular_edit.setText("abc")
    dialog.accept()
    assert dialog.saved is None
    assert dialog.blocks["name"].error_text != ""
    assert dialog.blocks["regular_price"].error_text != ""
    assert dialog.blocks["website_price"].error_text != ""
    assert repo.search() == []


def test_dialog_reports_duplicate_names(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    add_product(repo, "Fridge")
    dialog = ProductDialog(repo)
    qtbot.addWidget(dialog)
    dialog.name_edit.setText(" fridge ")
    dialog.regular_edit.setText("1")
    dialog.website_edit.setText("1")
    dialog.accept()
    assert dialog.saved is None
    assert "already exists" in dialog.blocks["name"].error_text


def test_edit_dialog_prefills_without_rounding(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    product = add_product(repo, regular="1234.567")
    dialog = ProductDialog(repo, product)
    qtbot.addWidget(dialog)
    assert dialog.regular_edit.text() == "1.234,567"
    dialog.accept()
    assert repo.get(product.id) == product  # unchanged value -> no-op update


def test_products_tab_lists_filters_and_archives(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    add_product(repo, "Fridge")
    add_product(repo, "Washer")
    tab = ProductsTab(repo)
    qtbot.addWidget(tab)
    assert tab.table_model.rowCount() == 2

    tab.search_edit.setText("wash")
    assert tab.table_model.rowCount() == 1
    assert tab.table_model.data(tab.table_model.index(0, 1)) == "5.000,00 TL"

    tab.table.selectRow(0)
    with qtbot.waitSignal(tab.products_changed):
        tab.archive_button.click()
    assert tab.table_model.rowCount() == 0

    tab.show_archived.setChecked(True)
    assert tab.table_model.rowCount() == 1
    tab.table.selectRow(0)
    assert tab.archive_button.text() == "Restore"
    with qtbot.waitSignal(tab.products_changed):
        tab.archive_button.click()
    assert [
        p.archived for p in repo.search("wash", include_archived=True)
    ] == [False]
