from decimal import Decimal as D
from typing import Any

from PySide6.QtWidgets import QHeaderView

from arcelikSalesHelper.domain.products import ProductDraft
from arcelikSalesHelper.domain.result import Ok
from arcelikSalesHelper.infrastructure.repositories import ProductRepository
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
    assert "zaten var" in dialog.blocks["name"].error_text


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
    assert tab.table.alternatingRowColors()
    assert not tab.table.showGrid()
    assert tab.table.verticalHeader().defaultSectionSize() == 40
    assert tab.table.horizontalHeader().minimumSectionSize() == 110
    assert (
        tab.table.horizontalHeader().sectionResizeMode(0)
        == QHeaderView.ResizeMode.Interactive
    )

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
    assert tab.archive_button.text() == "Geri yükle"
    with qtbot.waitSignal(tab.products_changed):
        tab.archive_button.click()
    assert [
        p.archived for p in repo.search("wash", include_archived=True)
    ] == [False]


def test_products_table_shows_yok_for_zero_website_price(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    product = add_product(repo, "No website offer", regular="38299", website="0")
    tab = ProductsTab(repo)
    qtbot.addWidget(tab)

    assert tab.table_model.data(tab.table_model.index(0, 2)) == "YOK"
    assert repo.get(product.id).website_price == D(0)
