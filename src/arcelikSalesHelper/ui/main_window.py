from __future__ import annotations

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

from arcelikSalesHelper.constants import DISPLAY_NAME
from arcelikSalesHelper.infrastructure.repositories import ProductRepository
from arcelikSalesHelper.paths import AppPaths

from .calculator_tab import CalculatorTab
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

        repo = ProductRepository(conn)
        self.products_tab = ProductsTab(repo)
        self.calculator_tab = CalculatorTab(repo)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.products_tab, "Products")
        self.tabs.addTab(self.calculator_tab, "Calculator")
        self.tabs.addTab(
            _placeholder("Calculation history arrives in milestone 5."),
            "History",
        )
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

    def _on_save_requested(self, _evaluation: object) -> None:
        # Replaced by the history save in M5.
        QMessageBox.information(
            self,
            "Not available yet",
            "Saving calculations is added in milestone 5.",
        )
