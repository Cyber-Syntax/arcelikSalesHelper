from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from arcelikSalesHelper import __version__
from arcelikSalesHelper import strings as T
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
from .common import show_warning
from .settings_tab import SettingsTab, describe_failure
from .theme import FONT_SCALE_KEY, install_material_theme, load_font_scale

BANNER_STYLE = "background-color: #d32f2f; color: white; padding: 6px;"

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self,
        conn: sqlite3.Connection,
        paths: AppPaths,
        backups: BackupManager | None = None,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(DISPLAY_NAME)
        self._settings = settings if settings is not None else QSettings()
        self._font_scale = load_font_scale(self._settings)
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1280, 820)
        else:
            available = screen.availableGeometry()
            self.resize(
                max(1, round(available.width() * 0.95)),
                max(1, round(available.height() * 0.90)),
            )

        self._conn = conn
        self._backups = backups
        repo = ProductRepository(conn)
        self._history_repo = HistoryRepository(conn)
        self.products_tab = ProductsTab(repo, conn, backups)
        self.calculator_tab = CalculatorTab(repo)
        self.calculator_tab.set_font_scale(self._font_scale)
        self.history_tab = HistoryTab(self._history_repo)
        self.settings_tab = SettingsTab(
            paths,
            backups,
            font_scale=self._font_scale,
            on_font_scale_changed=self._set_font_scale,
        )

        self.tabs = QTabWidget()
        self.tabs.addTab(self.products_tab, T.TAB_PRODUCTS)
        self.tabs.addTab(self.calculator_tab, T.TAB_CALCULATOR)
        self.tabs.addTab(self.history_tab, T.TAB_HISTORY)
        self.tabs.addTab(self.settings_tab, T.TAB_SETTINGS)

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

    def _set_font_scale(self, percent: int) -> None:
        self._font_scale = percent
        self._settings.setValue(FONT_SCALE_KEY, percent)
        self._settings.sync()
        app = QApplication.instance()
        if app is not None:
            install_material_theme(app, percent)
        self.calculator_tab.set_font_scale(percent)

    # ---- backups ---------------------------------------------------------

    def refresh_backup_banner(self) -> None:
        if self._backups is None:
            self.backup_banner.hide()
            return
        failure = self._backups.status().failure
        if failure is None:
            self.backup_banner.hide()
            return
        self.backup_banner.setText(T.backup_banner(describe_failure(failure)))
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
            show_warning(
                self,
                T.BACKUP_CLOSE_FAILED_TITLE,
                T.backup_close_failed(result.error.message),
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
            return Err(T.calc_save_failed(str(exc)))
        return Ok(snapshot_id)

    def _on_save_requested(self, evaluation: object) -> None:
        if not isinstance(evaluation, TransactionEvaluation):
            return
        outcome = self.save_calculation(evaluation)
        if isinstance(outcome, Err):
            show_warning(self, T.CALC_NOT_SAVED_TITLE, outcome.error)
            return
        self.history_tab.reload(select_id=outcome.value)
        self.statusBar().showMessage(
            T.calc_saved_status(outcome.value), 8000
        )
