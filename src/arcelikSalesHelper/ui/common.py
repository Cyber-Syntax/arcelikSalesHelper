from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

ERROR_STYLE = "color: #d32f2f;"
HINT_STYLE = "color: gray;"
WARNING_STYLE = "color: #b26a00;"


def format_local_timestamp(iso_utc: str) -> str:
    """Stored UTC ISO-8601 -> local 'YYYY-MM-DD HH:MM' for display."""
    try:
        moment = datetime.strptime(iso_utc, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
    except ValueError:
        return iso_utc
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


class FieldBlock(QWidget):
    """An editor with an inline error line and a hint line underneath."""

    def __init__(self, editor: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.editor = editor
        self._error = QLabel()
        self._error.setStyleSheet(ERROR_STYLE)
        self._error.setWordWrap(True)
        self._error.hide()
        self._hint = QLabel()
        self._hint.setStyleSheet(HINT_STYLE)
        self._hint.setWordWrap(True)
        self._hint.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(editor)
        layout.addWidget(self._error)
        layout.addWidget(self._hint)

    def set_error(self, text: str | None) -> None:
        self._error.setText(text or "")
        self._error.setVisible(bool(text))

    def set_hint(self, text: str | None) -> None:
        self._hint.setText(text or "")
        self._hint.setVisible(bool(text))

    @property
    def error_text(self) -> str:
        return self._error.text()

    @property
    def hint_text(self) -> str:
        return self._hint.text()
