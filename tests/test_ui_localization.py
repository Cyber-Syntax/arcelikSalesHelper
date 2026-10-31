"""Milestone 1 exit checks for the screens: every primary screen, dialog and
standard button shows Turkish text and no known English label remains.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTableView,
    QTableWidget,
    QTabWidget,
    QWidget,
)

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.constants import DATA_DIR_ENV_VAR
from arcelikSalesHelper.domain.models import POS_LABEL
from arcelikSalesHelper.domain.products import ProductDraft
from arcelikSalesHelper.domain.result import Ok
from arcelikSalesHelper.infrastructure.backups import BackupManager
from arcelikSalesHelper.infrastructure.database import open_database
from arcelikSalesHelper.infrastructure.repositories import ProductRepository
from arcelikSalesHelper.paths import ensure_dirs, resolve_paths
from arcelikSalesHelper.ui.import_dialog import ImportDialog
from arcelikSalesHelper.ui.main_window import MainWindow
from arcelikSalesHelper.ui.products_tab import ProductDialog

# Capitalised label words of the old English UI (case-sensitive on purpose).
ENGLISH_LABELS = re.compile(
    r"\b(Quantity|Regular|Website|Gift|Manager|Save|Cancel|Search|Settings|History"
    r"|Products?|Calculator|Backup|Import|Archive|Restore|Notes|Name|Lines?|Prices?"
    r"|Edit|Add|Remove|Open|Close|Totals?|Fix|Enter|Choose|Select|Unit|Skip|Update"
    r"|Apply|Row|Column|Problem|Status|Show|Load|Move|Optional|Result|Option"
    r"|Standard|Exact|Shown|Informational|Coupon|Effective|Discount)\b"
)


def english(texts: list[str]) -> list[str]:
    return [t for t in texts if ENGLISH_LABELS.search(t)]


def collect_texts(root: QWidget) -> list[str]:
    """Everything a person can read in ``root``: labels, buttons, titles,
    placeholders, tooltips, tab names, combo items, table headers and cells.
    Editable text is skipped on purpose (it is data, not interface text).
    """
    out: list[str] = []
    for w in [root, *root.findChildren(QWidget)]:
        out.extend((w.toolTip(), w.windowTitle()))
        if isinstance(w, QLabel) or isinstance(w, QAbstractButton):
            out.append(w.text())
        elif isinstance(w, QGroupBox):
            out.append(w.title())
        elif isinstance(w, QLineEdit):
            out.append(w.placeholderText())
        elif isinstance(w, QComboBox):
            out.extend(w.itemText(i) for i in range(w.count()))
        elif isinstance(w, QTabWidget):
            out.extend(w.tabText(i) for i in range(w.count()))
        elif isinstance(w, QTableWidget):
            for c in range(w.columnCount()):
                header = w.horizontalHeaderItem(c)
                out.append("" if header is None else header.text())
            for r in range(w.rowCount()):
                for c in range(w.columnCount()):
                    item = w.item(r, c)
                    out.append("" if item is None else item.text())
        elif isinstance(w, QTableView):
            model = w.model()
            out.extend(
                str(model.headerData(c, w.horizontalHeader().orientation()))
                for c in range(model.columnCount())
            )
    return [t for t in out if t.strip()]


@pytest.fixture
def env(qtbot: object, tmp_path):  # type: ignore[no-untyped-def]
    paths = ensure_dirs(resolve_paths({DATA_DIR_ENV_VAR: str(tmp_path)}))
    opened = open_database(paths.db_path)
    assert isinstance(opened, Ok)
    conn = opened.value
    window = MainWindow(conn, paths, BackupManager(conn, paths.backup_dir))
    qtbot.addWidget(window)  # type: ignore[attr-defined]
    window.show()
    yield window, conn, paths
    window.close()
    conn.close()


def _fill_valid_line(window: MainWindow) -> None:
    line = window.calculator_tab.rows[0].line
    line.name_edit.setText("Buzdolabı")
    line.regular_edit.setText("145.298,00")
    line.website_edit.setText("132.798,00")
    line.manager_edit.setText("112.000,00")
    line.gift_name_edit.setText("TKM 9961")


def test_tabs_and_window_are_turkish(env) -> None:  # type: ignore[no-untyped-def]
    window, _conn, _paths = env
    tabs = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert tabs == [
        T.TAB_PRODUCTS,
        T.TAB_CALCULATOR,
        T.TAB_HISTORY,
        T.TAB_SETTINGS,
    ]
    assert english(collect_texts(window)) == []


def test_calculator_with_valid_input_is_turkish(env) -> None:  # type: ignore[no-untyped-def]
    window, _conn, _paths = env
    _fill_valid_line(window)
    assert window.calculator_tab.evaluation.valid
    texts = collect_texts(window.calculator_tab)
    assert english(texts) == []
    assert POS_LABEL in texts
    assert T.SEC_WEBSITE_OPTION in texts and T.SEC_GIFT_OPTION in texts
    assert any(text.startswith(T.LBL_DISCOUNT_AMOUNT) for text in texts)
    assert T.LBL_TOTAL_DISCOUNT in texts
    assert "Bu nasıl hesaplandı" not in texts
    assert "%10 bazı" not in texts
    assert "bilgilendirme amaçlıdır" not in texts
    assert window.calculator_tab.save_button.text() == T.BTN_SAVE_CALCULATION


def test_inline_errors_and_hints_are_turkish(env) -> None:  # type: ignore[no-untyped-def]
    window, _conn, _paths = env
    line = window.calculator_tab.rows[0].line
    line.regular_edit.setText("abc")
    assert line.blocks["regular_price"].error_text == T.MONEY_CHARS
    line.regular_edit.setText("1.234")
    assert line.blocks["regular_price"].hint_text == T.money_ambiguous_hint(
        "1.234,00 TL"
    )


def test_history_tab_shows_a_saved_calculation_in_turkish(env) -> None:  # type: ignore[no-untyped-def]
    window, _conn, _paths = env
    _fill_valid_line(window)
    outcome = window.save_calculation(window.calculator_tab.evaluation)
    assert isinstance(outcome, Ok)
    window.history_tab.reload(select_id=outcome.value)
    texts = collect_texts(window.history_tab)
    assert english(texts) == []
    assert T.LBL_DISCOUNT_AMOUNT in texts
    assert T.LBL_TOTAL_DISCOUNT in texts
    assert "Bu nasıl hesaplandı" not in texts
    assert "%10 bazı" not in texts
    assert T.NOTE_HISTORY_FROZEN in texts


def test_settings_tab_and_backup_banner_are_turkish(env) -> None:  # type: ignore[no-untyped-def]
    window, _conn, _paths = env
    assert english(collect_texts(window.settings_tab)) == []
    window.settings_tab.backup_button.click()
    assert window.settings_tab.feedback.text().startswith("Yedek oluşturuldu")


def _buttons(dialog: QWidget) -> list[str]:
    box = dialog.findChild(QDialogButtonBox)
    assert box is not None
    return [b.text() for b in box.buttons()]


def test_product_and_stock_dialogs_are_turkish(env, qtbot) -> None:  # type: ignore[no-untyped-def]
    _window, conn, _paths = env
    repo = ProductRepository(conn)
    added = repo.add(ProductDraft("Fırın", Decimal(5000), Decimal(4000)))
    assert isinstance(added, Ok)

    add = ProductDialog(repo)
    qtbot.addWidget(add)
    assert english(collect_texts(add)) == []
    assert sorted(_buttons(add)) == sorted([T.BTN_SAVE, T.BTN_CANCEL])
    add.name_edit.setText("")
    add.accept()
    assert add.blocks["name"].error_text == T.VAL_NAME_REQUIRED

    stock = StockDialog(repo, added.value)
    qtbot.addWidget(stock)
    assert english(collect_texts(stock)) == []
    assert sorted(_buttons(stock)) == sorted([T.BTN_SAVE, T.BTN_CANCEL])
    stock.quantity_edit.setText("-1")
    stock.accept()
    assert stock.block.error_text == T.STOCK_NEGATIVE


def test_import_dialog_is_turkish_including_row_errors(
    env, qtbot, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    _window, conn, _paths = env
    repo = ProductRepository(conn)
    repo.add(ProductDraft("Mevcut", Decimal(100), Decimal(90)))
    csv_file = tmp_path / "urunler.csv"
    csv_file.write_text(
        "product_name,regular_price,website_discounted_price\n"
        "Mevcut,200,150\nYeni,10,5\nBozuk,abc,1\n",
        encoding="utf-8",
    )
    dialog = ImportDialog(repo, conn)
    qtbot.addWidget(dialog)
    dialog.load_file(csv_file)
    texts = collect_texts(dialog)
    assert english(texts) == []
    assert T.STATUS_CONFLICT in texts and T.STATUS_NEW in texts
    assert T.MONEY_CHARS in texts


def test_standard_buttons_use_turkish_text(env, qtbot) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QMessageBox

    from arcelikSalesHelper.ui.common import localize_buttons

    box = QMessageBox(
        QMessageBox.Icon.Question,
        "t",
        "m",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    qtbot.addWidget(box)
    localize_buttons(box)
    texts = {b.text() for b in box.buttons()}
    assert texts == {T.BTN_YES, T.BTN_NO}
    assert re.fullmatch(r"[A-Za-zİıÖöÜüÇçĞğŞş]+", T.BTN_NO)
