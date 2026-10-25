import sqlite3
from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import QGroupBox, QLabel

from arcelikSalesHelper.constants import DATA_DIR_ENV_VAR
from arcelikSalesHelper.domain.models import POS_LABEL
from arcelikSalesHelper.infrastructure.history_repository import (
    HistoryRepository,
)
from arcelikSalesHelper.paths import resolve_paths
from arcelikSalesHelper.ui.history_tab import HistoryTab
from arcelikSalesHelper.ui.main_window import MainWindow

from .test_calculator_tab import fill_two
from .test_history_repo import make_record


def detail_titles(tab: HistoryTab) -> list[str]:
    return [
        b.title() for b in tab.detail_scroll.widget().findChildren(QGroupBox)
    ]


def detail_texts(tab: HistoryTab) -> list[str]:
    return [
        lb.text() for lb in tab.detail_scroll.widget().findChildren(QLabel)
    ]


def test_empty_history_shows_a_hint(qtbot, db: sqlite3.Connection) -> None:  # type: ignore[no-untyped-def]
    tab = HistoryTab(HistoryRepository(db))
    qtbot.addWidget(tab)
    assert tab.table.rowCount() == 0
    assert tab.count_label.text() == "No saved calculations yet."
    assert not tab.load_more_button.isEnabled()
    assert isinstance(tab.detail_scroll.widget(), QLabel)


def test_saving_from_the_calculator_lists_and_shows_the_snapshot(  # type: ignore[no-untyped-def]
    qtbot, db: sqlite3.Connection, tmp_path: Path
) -> None:
    paths = resolve_paths({DATA_DIR_ENV_VAR: str(tmp_path / "data")})
    window = MainWindow(db, paths)
    qtbot.addWidget(window)
    fill_two(window.calculator_tab)
    window.calculator_tab.save_button.click()

    tab = window.history_tab
    assert tab.table.rowCount() == 1
    assert tab.table.item(0, 1).text() == "Fridge, Washer"
    assert tab.table.item(0, 2).text() == "2"
    assert tab.table.item(0, 3).text() == "20.500,00 TL"
    assert tab.selected_id() == 1
    titles = detail_titles(tab)
    assert {
        "Line 1: Fridge",
        "Line 2: Washer",
        "Transaction totals",
        POS_LABEL,
    } <= set(titles)
    assert "saved" in window.statusBar().currentMessage()
    assert (
        window.calculator_tab.evaluation.valid
    )  # the calculator keeps its inputs


def test_detail_is_rendered_from_stored_rows_without_recalculating(  # type: ignore[no-untyped-def]
    qtbot, db: sqlite3.Connection, monkeypatch
) -> None:
    repo = HistoryRepository(db)
    repo.save(make_record())
    tab = HistoryTab(repo)
    qtbot.addWidget(tab)

    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("history must never recalculate")

    for target in (
        "arcelikSalesHelper.domain.pricing.calculate_line",
        "arcelikSalesHelper.application.calculator.calculate_line",
        "arcelikSalesHelper.application.calculator.calculate_transaction",
    ):
        monkeypatch.setattr(target, boom)

    tab.table.selectRow(0)
    assert "20.500,00 TL" in detail_texts(tab)


def test_corrupt_snapshot_shows_a_message_instead_of_crashing(  # type: ignore[no-untyped-def]
    qtbot, db: sqlite3.Connection
) -> None:
    repo = HistoryRepository(db)
    repo.save(replace(make_record(), totals_json="{"))
    tab = HistoryTab(repo)
    qtbot.addWidget(tab)
    tab.table.selectRow(0)
    widget = tab.detail_scroll.widget()
    assert isinstance(widget, QLabel) and "could not be read" in widget.text()


def test_load_older_pages_through_the_list(
    qtbot, db: sqlite3.Connection
) -> None:  # type: ignore[no-untyped-def]
    repo = HistoryRepository(db)
    for _ in range(3):
        repo.save(make_record())
    tab = HistoryTab(repo, page_size=2)
    qtbot.addWidget(tab)
    assert tab.table.rowCount() == 2 and tab.load_more_button.isEnabled()
    tab.load_more_button.click()
    assert tab.table.rowCount() == 3
    ids = [tab.table.item(r, 0).data(0x0100) for r in range(3)]  # Qt.UserRole
    assert ids == [3, 2, 1]
    tab.load_more_button.click()  # nothing older: the button turns off
    assert not tab.load_more_button.isEnabled()
