from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from arcelikSalesHelper.domain.result import Err, Ok
from arcelikSalesHelper.infrastructure.backups import (
    KEEP_VERIFIED_BACKUPS,
    BackupFailure,
    BackupManager,
    BackupReason,
)
from arcelikSalesHelper.paths import AppPaths

from .common import (
    ERROR_STYLE,
    HINT_STYLE,
    SUCCESS_STYLE,
    format_local_timestamp,
)

REASON_LABELS = {
    "baseline": "initial backup",
    "startup": "startup",
    "close": "on close",
    "pre_migration": "before upgrade",
    "pre_import": "before import",
    "manual": "manual",
}


def describe_failure(failure: BackupFailure) -> str:
    label = REASON_LABELS.get(failure.reason, failure.reason or "unknown")
    return (
        f"The last backup ({label}, {format_local_timestamp(failure.at)}) failed: "
        f"{failure.message}"
    )


def open_folder(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class SettingsTab(QWidget):
    backup_finished = Signal()  # after a manual backup, success or failure

    def __init__(
        self,
        paths: AppPaths,
        manager: BackupManager | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._paths = paths
        self._manager = manager

        self.db_edit = self._path_edit(paths.db_path)
        self.backup_dir_edit = self._path_edit(paths.backup_dir)
        self.open_data_button = QPushButton("Open folder")
        self.open_backup_button = QPushButton("Open folder")
        self.latest_label = QLabel()
        self.latest_label.setWordWrap(True)
        self.count_label = QLabel()
        self.count_label.setStyleSheet(HINT_STYLE)
        self.failure_label = QLabel()
        self.failure_label.setWordWrap(True)
        self.failure_label.setStyleSheet(ERROR_STYLE)
        self.failure_label.hide()
        self.backup_button = QPushButton("Back up now")
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        note = QLabel(
            "Backups are stored on the same disk as the database, so they do not protect "
            f"against disk failure. The newest {KEEP_VERIFIED_BACKUPS} verified backups are kept."
        )
        note.setWordWrap(True)
        note.setStyleSheet(HINT_STYLE)

        form = QFormLayout()
        form.addRow(
            "Database", self._with_button(self.db_edit, self.open_data_button)
        )
        form.addRow(
            "Backup folder",
            self._with_button(self.backup_dir_edit, self.open_backup_button),
        )
        form.addRow("Latest successful backup", self.latest_label)
        buttons = QHBoxLayout()
        buttons.addWidget(self.backup_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.count_label)
        layout.addWidget(self.failure_label)
        layout.addLayout(buttons)
        layout.addWidget(self.feedback)
        layout.addWidget(note)
        layout.addStretch(1)

        self.open_data_button.clicked.connect(
            lambda _c=False: open_folder(paths.data_dir)
        )
        self.open_backup_button.clicked.connect(
            lambda _c=False: open_folder(paths.backup_dir)
        )
        self.backup_button.clicked.connect(lambda _c=False: self._backup_now())
        self.refresh()

    @staticmethod
    def _path_edit(path: Path) -> QLineEdit:
        edit = QLineEdit(str(path))
        edit.setReadOnly(True)  # selectable and copyable, not editable
        edit.setCursorPosition(0)
        return edit

    @staticmethod
    def _with_button(edit: QLineEdit, button: QPushButton) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return box

    def refresh(self) -> None:
        if self._manager is None:
            self.latest_label.setText("Backups are not enabled.")
            self.count_label.setText("")
            self.failure_label.hide()
            self.backup_button.setEnabled(False)
            return
        status = self._manager.status()
        if status.latest is None:
            self.latest_label.setText("No backup yet.")
        else:
            label = REASON_LABELS.get(
                status.latest.reason, status.latest.reason
            )
            self.latest_label.setText(
                f"{format_local_timestamp(status.latest.created_at_iso)} · {label} · "
                f"{status.latest.path.name}"
            )
        self.count_label.setText(
            f"{status.count} verified backup(s) in the backup folder."
        )
        if status.failure is None:
            self.failure_label.hide()
        else:
            self.failure_label.setText(describe_failure(status.failure))
            self.failure_label.show()

    def _backup_now(self) -> None:
        if self._manager is None:
            return
        self.backup_button.setEnabled(False)
        try:
            result = self._manager.run(BackupReason.MANUAL)
        finally:
            self.backup_button.setEnabled(True)
        match result:
            case Ok(info):
                self.feedback.setStyleSheet(SUCCESS_STYLE)
                self.feedback.setText(
                    f"Backup created and verified: {info.path.name}"
                )
            case Err(error):
                self.feedback.setStyleSheet(ERROR_STYLE)
                self.feedback.setText(f"Backup failed: {error.message}")
        self.refresh()
        self.backup_finished.emit()
