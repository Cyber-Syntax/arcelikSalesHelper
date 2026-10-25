from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
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
from arcelikSalesHelper.infrastructure.backups import BackupManager
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
from .settings_tab import SettingsTab, describe_failure

BANNER_STYLE = "background-color: #d32f2f; color: white; padding: 6px;"

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self,
        conn: sqlite3.Connection,
        paths: AppPaths,
        backups: BackupManager | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(DISPLAY_NAME)
        self.resize(1100, 720)

        self._conn = conn
        self._backups = backups
        repo = ProductRepository(conn)
        self._history_repo = HistoryRepository(conn)
        self.products_tab = ProductsTab(repo, conn, backups)
        self.calculator_tab = CalculatorTab(repo)
        self.history_tab = HistoryTab(self._history_repo)
        self.settings_tab = SettingsTab(paths, backups)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.products_tab, "Products")
        self.tabs.addTab(self.calculator_tab, "Calculator")
        self.tabs.addTab(self.history_tab, "History")
        self.tabs.addTab(self.settings_tab, "Settings")

        self.backup_banner = QLabel()
        self.backup_banner.setWordWrap(True)
        self.backup_banner.setStyleSheet(BANNER_STYLE)
        self.backup_banner.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.backup_banner.hide()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.backup_banner)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(container)

        self.products_tab.products_changed.connect(
            self.calculator_tab.refresh_products
        )
        self.calculator_tab.save_requested.connect(self._on_save_requested)
        self.settings_tab.backup_finished.connect(self.refresh_backup_banner)
        self.tabs.currentChanged.connect(
            lambda _i: self.settings_tab.refresh()
        )
        self.products_tab.import_finished.connect(self.refresh_backup_banner)
        self.products_tab.import_finished.connect(self.settings_tab.refresh)
        self.refresh_backup_banner()

    # ---- backups ---------------------------------------------------------

    def refresh_backup_banner(self) -> None:
        if self._backups is None:
            self.backup_banner.hide()
            return
        failure = self._backups.status().failure
        if failure is None:
            self.backup_banner.hide()
            return
        self.backup_banner.setText(
            f"⚠ {describe_failure(failure)} Recent changes may not be backed up. "
            "Open the Settings tab and choose “Back up now”."
        )
        self.backup_banner.show()

    def shutdown_backup(self, interactive: bool = True) -> None:
        """Backup on clean close when the database changed. Safe to call twice:
        once a backup succeeded there are no changes left to back up.
        """
        if self._backups is None:
            return
        try:
            result = self._backups.run_close_backup_if_needed()
        except sqlite3.Error:
            log.exception("Backup on close could not run")
            return
        if isinstance(result, Err) and interactive:
            QMessageBox.warning(
                self,
                "Backup on close failed",
                f"{result.error.message}\n\nThe application will close anyway. "
                "Start it again and use “Back up now” in Settings.",
            )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        self.shutdown_backup(interactive=True)
        super().closeEvent(event)

    # ---- history ---------------------------------------------------------

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
            log.exception("Saving the calculation failed")
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
