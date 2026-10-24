from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from arcelikSalesHelper.application.calculator import (
    Evaluation,
    FieldError,
    FieldHint,
    LineForm,
    ResultView,
    Section,
    evaluate_line,
)
from arcelikSalesHelper.domain.formatting import format_money_input
from arcelikSalesHelper.domain.models import ManagerMode
from arcelikSalesHelper.domain.products import Product
from arcelikSalesHelper.infrastructure.repositories import ProductRepository

from .common import HINT_STYLE, WARNING_STYLE, FieldBlock

ONE_OFF_LABEL = "One-off product (type below)"


class CalculatorLineWidget(QWidget):
    """Inputs of one calculator line. Holds no formulas; emits ``changed``.

    M4 reuses this class once per line.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._updating = False

        self.product_combo = QComboBox()
        self.product_combo.addItem(ONE_OFF_LABEL, None)
        self.name_edit = QLineEdit()
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 9999)
        self.regular_edit = QLineEdit()
        self.regular_edit.setPlaceholderText("for example 5.000,00")
        self.website_edit = QLineEdit()
        self.website_edit.setPlaceholderText("for example 4.000,00")
        self.coupon_edit = QLineEdit()
        self.coupon_edit.setPlaceholderText("0,00")
        self.gift_check = QCheckBox("Gift included")
        self.gift_name_edit = QLineEdit()
        self.manager_edit = QLineEdit()
        self.manager_edit.setPlaceholderText("optional")
        self.unit_radio = QRadioButton("Unit price")
        self.line_radio = QRadioButton("Total line price")
        self.unit_radio.setChecked(True)

        mode_box = QWidget()
        mode_layout = QHBoxLayout(mode_box)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.addWidget(self.unit_radio)
        mode_layout.addWidget(self.line_radio)
        mode_layout.addStretch(1)

        self.blocks = {
            "product_name": FieldBlock(self.name_edit),
            "quantity": FieldBlock(self.quantity_spin),
            "regular_price": FieldBlock(self.regular_edit),
            "website_price": FieldBlock(self.website_edit),
            "coupon": FieldBlock(self.coupon_edit),
            "manager_value": FieldBlock(self.manager_edit),
            "manager_mode": FieldBlock(mode_box),
        }

        form = QFormLayout(self)
        form.addRow("Product", self.product_combo)
        form.addRow("Name", self.blocks["product_name"])
        form.addRow("Quantity", self.blocks["quantity"])
        form.addRow(
            "Regular / first price (unit)", self.blocks["regular_price"]
        )
        form.addRow(
            "Website discounted price (unit)", self.blocks["website_price"]
        )
        form.addRow("Additional coupon (per unit)", self.blocks["coupon"])
        form.addRow("", self.gift_check)
        form.addRow("Gift name", self.gift_name_edit)
        form.addRow("Manager-provided value", self.blocks["manager_value"])
        form.addRow("Manager value is a", self.blocks["manager_mode"])

        for edit in (
            self.name_edit,
            self.regular_edit,
            self.website_edit,
            self.coupon_edit,
            self.gift_name_edit,
            self.manager_edit,
        ):
            edit.textChanged.connect(self._emit)
        self.quantity_spin.valueChanged.connect(self._emit)
        self.gift_check.toggled.connect(self._emit)
        self.unit_radio.toggled.connect(self._emit)
        self.product_combo.currentIndexChanged.connect(
            self._on_product_changed
        )

    # ---- state -----------------------------------------------------------

    def _emit(self, *_args: object) -> None:
        if not self._updating:
            self.changed.emit()

    def selected_product(self) -> Product | None:
        data = self.product_combo.currentData()
        return data if isinstance(data, Product) else None

    def form(self) -> LineForm:
        product = self.selected_product()
        return LineForm(
            product_name=self.name_edit.text(),
            quantity=self.quantity_spin.value(),
            regular_price=self.regular_edit.text(),
            website_price=self.website_edit.text(),
            coupon=self.coupon_edit.text(),
            gift_selected=self.gift_check.isChecked(),
            gift_name=self.gift_name_edit.text(),
            manager_value=self.manager_edit.text(),
            manager_mode=ManagerMode.LINE
            if self.line_radio.isChecked()
            else ManagerMode.UNIT,
            product_id=None if product is None else product.id,
        )

    def set_products(self, products: Sequence[Product]) -> None:
        """Reload the picker, keeping the selection when the product still exists.

        Field values are never touched here, so a product that was archived or
        edited meanwhile does not change what the user is looking at.
        """
        current = self.selected_product()
        self._updating = True
        try:
            self.product_combo.clear()
            self.product_combo.addItem(ONE_OFF_LABEL, None)
            for product in products:
                self.product_combo.addItem(product.name, product)
            index = next(
                (
                    i
                    for i in range(1, self.product_combo.count())
                    if current is not None
                    and self.product_combo.itemData(i).id == current.id
                ),
                0,
            )
            self.product_combo.setCurrentIndex(index)
            self._apply_name_lock()
        finally:
            self._updating = False
        self.changed.emit()

    def _apply_name_lock(self) -> None:
        self.name_edit.setReadOnly(self.selected_product() is not None)

    def _on_product_changed(self, _index: int) -> None:
        if self._updating:
            return
        product = self.selected_product()
        self._updating = True
        try:
            if product is not None:
                # Copy, never link: later edits here do not write back to the product.
                self.name_edit.setText(product.name)
                self.regular_edit.setText(
                    format_money_input(product.regular_price)
                )
                self.website_edit.setText(
                    format_money_input(product.website_price)
                )
                self.gift_name_edit.setText(product.default_gift_name or "")
            self._apply_name_lock()
        finally:
            self._updating = False
        self.changed.emit()

    def set_feedback(
        self, errors: Sequence[FieldError], hints: Sequence[FieldHint]
    ) -> None:
        for block in self.blocks.values():
            block.set_error(None)
            block.set_hint(None)
        for error in errors:
            block = self.blocks.get(error.field)
            if block is not None and not error.incomplete:
                block.set_error(error.message)
        for hint in hints:
            block = self.blocks.get(hint.field)
            if block is not None:
                block.set_hint(hint.message)


class Collapsible(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.toggle_button = QToolButton()
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setStyleSheet("QToolButton { border: none; }")
        self.toggle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.body.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.body)
        self.toggle_button.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self.toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
        self.body.setVisible(checked)

    def set_lines(self, lines: Sequence[str]) -> None:
        self.body.setText("\n".join(lines))


def _clear(layout: QLayout) -> None:
    while (item := layout.takeAt(0)) is not None:
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


class ResultPanel(QWidget):
    """Renders a ``ResultView``. Contains no calculations."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet(HINT_STYLE)

        self.content = QWidget()
        self._sections = QVBoxLayout()
        self._warnings = QLabel()
        self._warnings.setWordWrap(True)
        self._warnings.setStyleSheet(WARNING_STYLE)
        self._explain = Collapsible("How this was calculated")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addLayout(self._sections)
        content_layout.addWidget(self._warnings)
        content_layout.addWidget(self._explain)

        layout = QVBoxLayout(self)
        layout.addWidget(self.message)
        layout.addWidget(self.content)
        layout.addStretch(1)
        self.show_message("Enter the product name and prices to see results.")

    def show_message(self, text: str) -> None:
        self.message.setText(text)
        self.message.show()
        self.content.hide()  # never show stale results

    def show_view(self, view: ResultView) -> None:
        _clear(self._sections)
        for section in view.sections:
            self._sections.addWidget(self._section_box(section))
        self._warnings.setText("\n".join(f"⚠ {w}" for w in view.warnings))
        self._warnings.setVisible(bool(view.warnings))
        self._explain.set_lines(view.explanation)
        self.message.hide()
        self.content.show()

    @staticmethod
    def _section_box(section: Section) -> QGroupBox:
        box = QGroupBox(section.title)
        grid = QGridLayout(box)
        grid.setColumnStretch(0, 1)
        for i, row in enumerate(section.rows):
            label = QLabel(row.label)
            value = QLabel(row.value)
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            value.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            if row.tooltip:
                value.setToolTip(row.tooltip)
            grid.addWidget(label, i, 0)
            grid.addWidget(value, i, 1)
        if section.note:
            note = QLabel(section.note)
            note.setWordWrap(True)
            note.setStyleSheet(HINT_STYLE)
            grid.addWidget(note, len(section.rows), 0, 1, 2)
        return box


class CalculatorTab(QWidget):
    """Controller: widget -> LineForm -> evaluate_line -> render."""

    save_requested = Signal(object)  # Evaluation; wired to history in M5

    def __init__(
        self, repo: ProductRepository, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._repo = repo
        self.evaluation = Evaluation()

        self.line = CalculatorLineWidget()
        self.panel = ResultPanel()
        self.save_button = QPushButton("Save calculation")
        self.save_button.setEnabled(False)

        left = QScrollArea()
        left.setWidgetResizable(True)
        left.setWidget(self.line)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(self.panel)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(right_scroll, 1)
        right_layout.addWidget(self.save_button)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([430, 570])
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self.line.changed.connect(self.recalculate)
        self.save_button.clicked.connect(
            lambda _c: self.save_requested.emit(self.evaluation)
        )
        self.refresh_products()

    def refresh_products(self) -> None:
        self.line.set_products(
            self._repo.search()
        )  # emits changed -> recalculate

    def recalculate(self) -> None:
        evaluation = evaluate_line(self.line.form())
        self.evaluation = evaluation
        self.line.set_feedback(evaluation.errors, evaluation.hints)
        if evaluation.view is not None:
            self.panel.show_view(evaluation.view)
        elif evaluation.incomplete_only:
            self.panel.show_message(
                "Enter the product name and prices to see results."
            )
        else:
            self.panel.show_message(
                "Fix the highlighted fields to see results."
            )
        self.save_button.setEnabled(evaluation.valid)
