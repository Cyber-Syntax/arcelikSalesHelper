from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from arcelikSalesHelper import strings as T
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
from .theme import DEFAULT_FONT_SCALE, FONT_SCALE_CHOICES

REASON_LABELS = T.BACKUP_REASON_LABELS


def describe_failure(failure: BackupFailure) -> str:
    label = REASON_LABELS.get(
        failure.reason, failure.reason or T.BACKUP_REASON_UNKNOWN
    )
    return T.describe_backup_failure(
        label, format_local_timestamp(failure.at), failure.message
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
        *,
        font_scale: int = DEFAULT_FONT_SCALE,
        on_font_scale_changed: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._paths = paths
        self._manager = manager
        self._on_font_scale_changed = on_font_scale_changed

        self.font_scale_combo = QComboBox()
        for percent in FONT_SCALE_CHOICES:
            self.font_scale_combo.addItem(f"{percent}%", percent)
        index = self.font_scale_combo.findData(font_scale)
        self.font_scale_combo.setCurrentIndex(max(index, 0))
        self.font_scale_note = QLabel(T.NOTE_UI_TEXT_SIZE)
        self.font_scale_note.setWordWrap(True)
        self.font_scale_note.setStyleSheet(HINT_STYLE)

        self.db_edit = self._path_edit(paths.db_path)
        self.backup_dir_edit = self._path_edit(paths.backup_dir)
        self.open_data_button = QPushButton(T.BTN_OPEN_FOLDER)
        self.open_backup_button = QPushButton(T.BTN_OPEN_FOLDER)
        self.latest_label = QLabel()
        self.latest_label.setWordWrap(True)
        self.count_label = QLabel()
        self.count_label.setStyleSheet(HINT_STYLE)
        self.failure_label = QLabel()
        self.failure_label.setWordWrap(True)
        self.failure_label.setStyleSheet(ERROR_STYLE)
        self.failure_label.hide()
        self.backup_button = QPushButton(T.BTN_BACKUP_NOW)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        note = QLabel(T.settings_disk_note(KEEP_VERIFIED_BACKUPS))
        note.setWordWrap(True)
        note.setStyleSheet(HINT_STYLE)

        form = QFormLayout()
        form.addRow(
            T.LBL_DATABASE,
            self._with_button(self.db_edit, self.open_data_button),
        )
        form.addRow(
            T.LBL_BACKUP_FOLDER,
            self._with_button(self.backup_dir_edit, self.open_backup_button),
        )
        form.addRow(T.LBL_LATEST_BACKUP, self.latest_label)
        form.addRow(T.LBL_UI_TEXT_SIZE, self.font_scale_combo)
        buttons = QHBoxLayout()
        buttons.addWidget(self.backup_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.count_label)
        layout.addWidget(self.font_scale_note)
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
        if on_font_scale_changed is not None:
            self.font_scale_combo.currentIndexChanged.connect(
                self._change_font_scale
            )
        self.refresh()

    def _change_font_scale(self, index: int) -> None:
        percent = self.font_scale_combo.itemData(index)
        if (
            isinstance(percent, int)
            and self._on_font_scale_changed is not None
        ):
            self._on_font_scale_changed(percent)

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
            self.latest_label.setText(T.BACKUPS_DISABLED)
            self.count_label.setText("")
            self.failure_label.hide()
            self.backup_button.setEnabled(False)
            return
        status = self._manager.status()
        if status.latest is None:
            self.latest_label.setText(T.NO_BACKUP_YET)
        else:
            label = REASON_LABELS.get(
                status.latest.reason, status.latest.reason
            )
            self.latest_label.setText(
                T.latest_backup_line(
                    format_local_timestamp(status.latest.created_at_iso),
                    label,
                    status.latest.path.name,
                )
            )
        self.count_label.setText(T.backup_count(status.count))
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
                self.feedback.setText(T.backup_ok(info.path.name))
            case Err(error):
                self.feedback.setStyleSheet(ERROR_STYLE)
                self.feedback.setText(T.backup_failed(error.message))
        self.refresh()
        self.backup_finished.emit()
