from decimal import Decimal as D
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.domain.products import ProductDraft
from arcelikSalesHelper.domain.result import Ok
from arcelikSalesHelper.domain.stock import StockSource
from arcelikSalesHelper.infrastructure.backups import BackupManager, list_backups
from arcelikSalesHelper.ui.import_dialog import ImportDialog
from arcelikSalesHelper.ui.products_tab import ProductsTab, StockDialog

HEADER = "product_name,regular_price,website_discounted_price"


@pytest.fixture(autouse=True)
def no_message_boxes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        QMessageBox,
        "exec",
        lambda _self: int(QMessageBox.StandardButton.Ok),
    )


def csv_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "in.csv"
    path.write_text(text, encoding="utf-8")
    return path


def add(repo, name="Fridge", regular="5000", website="4000"):  # type: ignore[no-untyped-def]
    result = repo.add(ProductDraft(name, D(regular), D(website)))
    assert isinstance(result, Ok)
    return result.value


def test_preview_conflicts_need_a_decision_before_apply(qtbot, repo, db, tmp_path) -> None:  # type: ignore[no-untyped-def]
    fridge = add(repo)
    dialog = ImportDialog(repo, db)
    qtbot.addWidget(dialog)
    dialog.load_file(csv_file(tmp_path, f'{HEADER}\nFridge,"5.500,00",4000\nOven,100,90\n'))

    assert dialog.table.rowCount() == 2
    assert [dialog.table.item(r, 1).text() for r in range(2)] == [
        T.STATUS_CONFLICT,
        T.STATUS_NEW,
    ]
    assert "5.000,00 TL → 5.500,00 TL" in dialog.table.item(0, 3).text()
    assert not dialog.apply_button.isEnabled()
    assert "çakışma" in dialog.status_label.text().lower()

    dialog.decision_combos[2].setCurrentIndex(1)  # Update
    assert dialog.apply_button.isEnabled()
    dialog.apply_button.click()

    assert dialog.summary is not None and (dialog.summary.updated, dialog.summary.created) == (1, 1)
    assert repo.get(fridge.id).regular_price == D("5500")  # type: ignore[union-attr]
    assert [p.name for p in repo.search("oven")] == ["Oven"]


def test_skip_leaves_the_product_alone(qtbot, repo, db, tmp_path) -> None:  # type: ignore[no-untyped-def]
    fridge = add(repo)
    dialog = ImportDialog(repo, db)
    qtbot.addWidget(dialog)
    dialog.load_file(csv_file(tmp_path, f"{HEADER}\nFridge,9000,8000\n"))
    dialog.decision_combos[2].setCurrentIndex(2)  # Skip
    dialog.apply_button.click()
    assert repo.get(fridge.id) == fridge


def test_row_errors_block_apply_until_valid_only_is_ticked(qtbot, repo, db, tmp_path) -> None:  # type: ignore[no-untyped-def]
    dialog = ImportDialog(repo, db)
    qtbot.addWidget(dialog)
    dialog.load_file(csv_file(tmp_path, f"{HEADER}\nOven,100,90\nBad,abc,1\n"))
    assert dialog.errors_table.rowCount() == 1
    assert dialog.errors_table.item(0, 0).text() == "3"
    assert not dialog.apply_button.isEnabled()

    dialog.valid_only_check.setChecked(True)
    assert dialog.apply_button.isEnabled()
    dialog.apply_button.click()
    assert [p.name for p in repo.search()] == ["Oven"]


def test_a_bad_header_shows_a_message_and_no_preview(qtbot, repo, db, tmp_path) -> None:  # type: ignore[no-untyped-def]
    dialog = ImportDialog(repo, db)
    qtbot.addWidget(dialog)
    dialog.load_file(csv_file(tmp_path, "name,price\nA,1\n"))
    assert "Geçersiz başlık" in dialog.file_error.text()
    assert dialog.table.rowCount() == 0 and not dialog.apply_button.isEnabled()


def test_a_backup_is_made_before_applying(qtbot, repo, db, tmp_path, clock) -> None:  # type: ignore[no-untyped-def]
    manager = BackupManager(db, tmp_path / "backups", clock)
    dialog = ImportDialog(repo, db, manager)
    qtbot.addWidget(dialog)
    dialog.load_file(csv_file(tmp_path, f"{HEADER}\nOven,100,90\n"))
    dialog.apply_button.click()
    assert [b.reason for b in list_backups(tmp_path / "backups")] == ["pre_import"]


def test_stock_file_preview_shows_old_and_new_quantity(qtbot, repo, db, tmp_path) -> None:  # type: ignore[no-untyped-def]
    fridge = add(repo)
    repo.set_quantity(fridge.id, 2, StockSource.MANUAL)
    dialog = ImportDialog(repo, db)
    qtbot.addWidget(dialog)
    dialog.load_file(csv_file(tmp_path, "product_name,quantity\nFridge,6\n"))
    assert dialog.table.item(0, 1).text() == T.STATUS_STOCK_UPDATE
    assert dialog.table.item(0, 5).text() == "2 → 6"
    dialog.apply_button.click()
    assert repo.get(fridge.id).quantity == 6  # type: ignore[union-attr]


# ---- quantity in the products tab ----------------------------------------


def test_stock_dialog_saves_and_validates(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    product = add(repo)
    dialog = StockDialog(repo, product)
    qtbot.addWidget(dialog)
    assert dialog.quantity_edit.text() == ""
    dialog.quantity_edit.setText("1,5")
    dialog.accept()
    assert dialog.saved is None and dialog.block.error_text != ""

    dialog.quantity_edit.setText("12")
    dialog.note_edit.setText("warehouse photo")
    dialog.accept()
    assert dialog.saved is not None and dialog.saved.quantity == 12


def test_stock_dialog_prefills_the_current_count(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    product = add(repo)
    counted = repo.set_quantity(product.id, 8, StockSource.MANUAL)
    assert isinstance(counted, Ok)
    dialog = StockDialog(repo, counted.value)
    qtbot.addWidget(dialog)
    assert dialog.quantity_edit.text() == "8"


def test_products_tab_shows_counts_and_gates_its_buttons(qtbot, repo) -> None:  # type: ignore[no-untyped-def]
    product = add(repo)
    tab = ProductsTab(repo)
    qtbot.addWidget(tab)
    assert tab.table_model.data(tab.table_model.index(0, 6)) == "—"
    assert not tab.stock_button.isEnabled() and not tab.import_button.isEnabled()

    repo.set_quantity(product.id, 1500, StockSource.MANUAL)
    tab.reload()
    assert tab.table_model.data(tab.table_model.index(0, 6)) == "1.500"
    assert tab.table_model.data(tab.table_model.index(0, 7)) != ""
    tab.table.selectRow(0)
    assert tab.stock_button.isEnabled()
