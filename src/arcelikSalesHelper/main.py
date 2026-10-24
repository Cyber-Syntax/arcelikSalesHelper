from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from PySide6.QtWidgets import QApplication, QMessageBox

from .constants import APP_NAME, COMPANY_NAME, DISPLAY_NAME
from .domain.result import Err
from .infrastructure.database import open_database
from .paths import ensure_dirs, resolve_paths
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
        QMessageBox.critical(
            None,
            "Unexpected error",
            f"An unexpected error occurred:\n{exc}\n\nDetails were written to:\n{log_path}",
        )

    sys.excepthook = hook


def main(argv: Sequence[str] | None = None) -> int:
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(COMPANY_NAME)
    app.setApplicationDisplayName(DISPLAY_NAME)

    try:
        paths = ensure_dirs(resolve_paths())
    except OSError as exc:
        QMessageBox.critical(
            None, "Cannot start", f"Cannot create the data folder:\n{exc}"
        )
        return 1
    configure_logging(paths.log_path)
    install_excepthook(paths.log_path)

    opened = open_database(paths.db_path)
    if isinstance(opened, Err):
        QMessageBox.critical(
            None, "Cannot open the database", opened.error.message
        )
        return 1
    conn = opened.value
    try:
        window = MainWindow(conn, paths)
        window.show()
        return app.exec()
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
