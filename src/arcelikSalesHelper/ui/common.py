from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from arcelikSalesHelper import strings as T

ERROR_STYLE = "color: #d32f2f;"
HINT_STYLE = "color: #475569;"
WARNING_STYLE = "color: #b26a00;"
SUCCESS_STYLE = "color: #2e7d32;"


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


# ---- Turkish dialog plumbing -------------------------------------------------

_BUTTON_TEXT = {
    "Ok": T.BTN_OK,
    "Cancel": T.BTN_CANCEL,
    "Save": T.BTN_SAVE,
    "Yes": T.BTN_YES,
    "No": T.BTN_NO,
    "Close": T.BTN_CLOSE,
}


def localize_buttons(box: QDialogButtonBox | QMessageBox) -> None:
    """Qt only translates standard buttons when its .qm files are found, which
    is not guaranteed in a packaged build. Set the Turkish text explicitly."""
    enum = (
        QMessageBox.StandardButton
        if isinstance(box, QMessageBox)
        else QDialogButtonBox.StandardButton
    )
    for name, text in _BUTTON_TEXT.items():
        button = box.button(getattr(enum, name))
        if button is not None:
            button.setText(text)
    button_box = (
        box
        if isinstance(box, QDialogButtonBox)
        else box.findChild(QDialogButtonBox)
    )
    if button_box is not None:
        order_enum = QDialogButtonBox.StandardButton
        left = next(
            (
                button_box.button(getattr(order_enum, name))
                for name in ("Yes", "Ok", "Save")
                if button_box.button(getattr(order_enum, name)) is not None
            ),
            None,
        )
        right = next(
            (
                button_box.button(getattr(order_enum, name))
                for name in ("Cancel", "No", "Close")
                if button_box.button(getattr(order_enum, name)) is not None
            ),
            None,
        )
        if left is not None and right is not None:
            layout = button_box.layout()
            layout.removeWidget(left)
            layout.removeWidget(right)
            layout.insertWidget(0, left)
            layout.addWidget(right)


def _show(
    parent: QWidget | None,
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton,
    default: QMessageBox.StandardButton | None = None,
) -> QMessageBox:
    box = QMessageBox(icon, title, text, buttons, parent)
    localize_buttons(box)
    if default is not None:
        box.setDefaultButton(default)
    box.exec()
    return box


def show_info(parent: QWidget | None, title: str, text: str) -> None:
    _show(parent, QMessageBox.Icon.Information, title, text, QMessageBox.StandardButton.Ok)


def show_warning(parent: QWidget | None, title: str, text: str) -> None:
    _show(parent, QMessageBox.Icon.Warning, title, text, QMessageBox.StandardButton.Ok)


def show_critical(parent: QWidget | None, title: str, text: str) -> None:
    _show(parent, QMessageBox.Icon.Critical, title, text, QMessageBox.StandardButton.Ok)


def ask_yes_no(parent: QWidget | None, title: str, text: str) -> bool:
    """Question dialog; "Hayır" is the default so Enter never confirms by accident."""
    yes, no = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No
    box = _show(parent, QMessageBox.Icon.Question, title, text, yes | no, no)
    return box.clickedButton() is box.button(yes)


def install_qt_translations(app: QCoreApplication) -> None:
    """Turkish locale plus Qt's own Turkish strings (file dialogs, context menus).

    Best effort: a missing translation file only means those few Qt-provided
    strings stay in English; every string of this application comes from
    ``strings.py`` and does not depend on it.
    """
    QLocale.setDefault(QLocale(QLocale.Language.Turkish, QLocale.Country.Turkey))
    directory = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for name in ("qtbase",):
        translator = QTranslator(app)
        if translator.load(QLocale(), name, "_", directory):
            app.installTranslator(translator)
