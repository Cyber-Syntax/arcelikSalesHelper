from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from PySide6.QtWidgets import QApplication

from . import strings as T
from .constants import APP_NAME, COMPANY_NAME, DISPLAY_NAME
from .domain.result import Err
from .infrastructure.backups import (
    BackupManager,
    BackupReason,
    PreMigrationBackup,
)
from .infrastructure.database import open_database
from .paths import ensure_dirs, resolve_paths
from .ui.common import install_qt_translations, show_critical
from .ui.main_window import MainWindow


def configure_logging(log_path: Path) -> None:
    handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def install_excepthook(log_path: Path) -> None:
    def hook(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logging.getLogger("app").critical(
            "Unhandled exception", exc_info=(exc_type, exc, tb)
        )
        show_critical(
            None, T.UNEXPECTED_ERROR_TITLE, T.unexpected_error(exc, log_path)
        )

    sys.excepthook = hook


def main(argv: Sequence[str] | None = None) -> int:
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(COMPANY_NAME)
    app.setApplicationDisplayName(DISPLAY_NAME)
    install_qt_translations(app)

    try:
        paths = ensure_dirs(resolve_paths())
    except OSError as exc:
        show_critical(
            None, T.CANNOT_START_TITLE, T.cannot_create_data_dir(exc)
        )
        return 1
    configure_logging(paths.log_path)
    install_excepthook(paths.log_path)

    fresh = not paths.db_path.exists() or paths.db_path.stat().st_size == 0
    pre_migration = PreMigrationBackup(paths.db_path, paths.backup_dir)
    opened = open_database(paths.db_path, on_before_migrate=pre_migration)
    if isinstance(opened, Err):
        show_critical(None, T.CANNOT_OPEN_DB_TITLE, opened.error.message)
        return 1
    conn = opened.value
    try:
        backups = BackupManager(conn, paths.backup_dir)
        if pre_migration.ran:
            backups.mark_dirty()  # the upgrade changed the database after the old-schema backup
        if fresh:
            backups.run(BackupReason.BASELINE)
        else:
            backups.run_startup_backup_if_needed()
        # A failed backup is recorded and shown as a banner; it never blocks startup.

        window = MainWindow(conn, paths, backups)
        app.aboutToQuit.connect(
            lambda: window.shutdown_backup(interactive=False)
        )
        window.show()
        return app.exec()
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
