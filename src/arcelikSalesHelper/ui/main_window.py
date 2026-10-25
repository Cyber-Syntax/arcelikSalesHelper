from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from arcelikSalesHelper import __version__
from arcelikSalesHelper.application.calculator import TransactionEvaluation
from arcelikSalesHelper.application.history import build_snapshot, to_utc_iso
from arcelikSalesHelper.constants import DISPLAY_NAME
from arcelikSalesHelper.domain.result import Err, Ok, Result
from arcelikSalesHelper.infrastructure.database import schema_version
from arcelikSalesHelper.infrastructure.history_repository import (
    HistoryRepository,
)
from arcelikSalesHelper.infrastructure.repositories import (
    ProductRepository,
    utc_now,
)
from arcelikSalesHelper.paths import AppPaths

from .calculator_tab import CalculatorTab
from .history_tab import HistoryTab
from .products_tab import ProductsTab


def _placeholder(text: str) -> QWidget:
    page = QWidget()
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    QVBoxLayout(page).addWidget(label)
    return page


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, paths: AppPaths) -> None:
        super().__init__()
        self.setWindowTitle(DISPLAY_NAME)
        self.resize(1100, 720)

        self._conn = conn
        repo = ProductRepository(conn)
        self._history_repo = HistoryRepository(conn)
        self.products_tab = ProductsTab(repo)
        self.calculator_tab = CalculatorTab(repo)
        self.history_tab = HistoryTab(self._history_repo)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.products_tab, "Products")
        self.tabs.addTab(self.calculator_tab, "Calculator")
        self.tabs.addTab(self.history_tab, "History")
        self.tabs.addTab(
            _placeholder(
                f"Database: {paths.db_path}\nBackups: {paths.backup_dir}\n\n"
                "Backup controls arrive in milestone 6."
            ),
            "Settings",
        )
        self.setCentralWidget(self.tabs)

        self.products_tab.products_changed.connect(
            self.calculator_tab.refresh_products
        )
        self.calculator_tab.save_requested.connect(self._on_save_requested)

    def save_calculation(
        self, evaluation: TransactionEvaluation
    ) -> Result[int, str]:
        built = build_snapshot(
            evaluation,
            created_at=to_utc_iso(utc_now()),
            app_version=__version__,
            schema_version=schema_version(self._conn),
        )
        if isinstance(built, Err):
            return Err(built.error)
        try:
            snapshot_id = self._history_repo.save(built.value)
        except sqlite3.Error as exc:
            logging.getLogger(__name__).exception(
                "Saving the calculation failed"
            )
            return Err(f"The calculation could not be saved: {exc}")
        return Ok(snapshot_id)

    def _on_save_requested(self, evaluation: object) -> None:
        if not isinstance(evaluation, TransactionEvaluation):
            return
        outcome = self.save_calculation(evaluation)
        if isinstance(outcome, Err):
            QMessageBox.warning(self, "Calculation not saved", outcome.error)
            return
        self.history_tab.reload(select_id=outcome.value)
        self.statusBar().showMessage(
            f"Calculation #{outcome.value} saved to history.", 8000
        )
