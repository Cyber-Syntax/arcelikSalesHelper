from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
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

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.application.calculator import (
    Evaluation,
    FieldError,
    FieldHint,
    LineForm,
    Section,
    TransactionEvaluation,
    evaluate_transaction,
)
from arcelikSalesHelper.domain.formatting import format_money_input
from arcelikSalesHelper.domain.models import POS_LABEL, ManagerMode
from arcelikSalesHelper.domain.products import Product
from arcelikSalesHelper.infrastructure.repositories import ProductRepository

from .common import HINT_STYLE, WARNING_STYLE, FieldBlock
from .theme import DEFAULT_FONT_SCALE

ONE_OFF_LABEL = T.ONE_OFF_LABEL


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
        self.regular_edit.setPlaceholderText(T.PH_REGULAR)
        self.website_edit = QLineEdit()
        self.website_edit.setPlaceholderText(T.PH_WEBSITE)
        self.gift_check = QCheckBox(T.CHK_GIFT)
        self.gift_name_edit = QLineEdit()
        self.manager_edit = QLineEdit()
        self.manager_edit.setPlaceholderText(T.PH_OPTIONAL)
        self.unit_radio = QRadioButton(T.RADIO_UNIT)
        self.line_radio = QRadioButton(T.RADIO_LINE)
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
            "website_discounted_price": FieldBlock(self.website_edit),
            "manager_value": FieldBlock(self.manager_edit),
            "manager_mode": FieldBlock(mode_box),
        }

        form = QFormLayout(self)
        form.addRow(T.FORM_PRODUCT, self.product_combo)
        form.addRow(T.FORM_NAME, self.blocks["product_name"])
        form.addRow(T.FORM_QUANTITY, self.blocks["quantity"])
        form.addRow(
            T.FORM_REGULAR, self.blocks["regular_price"]
        )
        form.addRow(
            T.FORM_WEBSITE, self.blocks["website_discounted_price"]
        )
        form.addRow("", self.gift_check)
        form.addRow(T.FORM_GIFT_NAME, self.gift_name_edit)
        form.addRow(T.FORM_MANAGER_VALUE, self.blocks["manager_value"])
        form.addRow(T.FORM_MANAGER_MODE, self.blocks["manager_mode"])

        for edit in (
            self.name_edit,
            self.regular_edit,
            self.website_edit,
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
            website_discounted_price=self.website_edit.text(),
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


def section_box(section: Section, *, role: str | None = None) -> QGroupBox:
    box = QGroupBox(section.title)
    if role is not None:
        box.setProperty("visualRole", role)
    grid = QGridLayout(box)
    grid.setColumnStretch(0, 1)
    for i, row in enumerate(section.rows):
        label = QLabel(row.label)
        label.setWordWrap(True)
        value = QLabel(row.value)
        value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        if row.label in (T.LBL_TEN_LINE_TOTAL, T.LBL_MANAGER_LINE_TOTAL):
            value.setProperty("amountRole", "emphasis")
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


class LineRow(QGroupBox):
    """One calculator line: header with move/remove buttons plus the input widget."""

    move_up = Signal(object)
    move_down = Signal(object)
    remove_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.line = CalculatorLineWidget()
        self.up_button = QToolButton()
        self.up_button.setText("↑")
        self.up_button.setToolTip(T.TIP_MOVE_UP)
        self.down_button = QToolButton()
        self.down_button.setText("↓")
        self.down_button.setToolTip(T.TIP_MOVE_DOWN)
        self.remove_button = QToolButton()
        self.remove_button.setText("✕")
        self.remove_button.setToolTip(T.TIP_REMOVE_LINE)

        header = QHBoxLayout()
        header.addStretch(1)
        header.addWidget(self.up_button)
        header.addWidget(self.down_button)
        header.addWidget(self.remove_button)
        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.line)

        self.up_button.clicked.connect(
            lambda _c=False: self.move_up.emit(self)
        )
        self.down_button.clicked.connect(
            lambda _c=False: self.move_down.emit(self)
        )
        self.remove_button.clicked.connect(
            lambda _c=False: self.remove_requested.emit(self)
        )

    def set_position(self, index: int, count: int) -> None:
        self.setTitle(T.line_title(index + 1))
        self.up_button.setEnabled(index > 0)
        self.down_button.setEnabled(index < count - 1)
        self.remove_button.setEnabled(count > 1)


class TransactionPanel(QWidget):
    """Renders a TransactionEvaluation. Contains no calculations."""

    OPTION_STACK_BREAKPOINT = 760

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards = QVBoxLayout()
        self._totals = QVBoxLayout()
        self._option_layouts: list[QBoxLayout] = []
        layout = QVBoxLayout(self)
        layout.addLayout(self._totals)
        layout.addLayout(self._cards)
        layout.addStretch(1)

    @staticmethod
    def _note(text: str, style: str = HINT_STYLE) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(style)
        return label

    def show_evaluation(self, evaluation: TransactionEvaluation) -> None:
        _clear(self._cards)
        _clear(self._totals)
        self._option_layouts.clear()
        if evaluation.totals_sections:
            sections = sorted(
                evaluation.totals_sections,
                key=lambda section: section.title != POS_LABEL,
            )
            for section in sections:
                if section.title == POS_LABEL:
                    summary, details = _pos_summary_boxes(section)
                    self._totals.addWidget(summary)
                    if details is not None:
                        self._totals.addWidget(details)
                else:
                    self._totals.addWidget(section_box(section))
        elif evaluation.pending_reason:
            self._totals.addWidget(self._note(evaluation.pending_reason))
        multiple_lines = len(evaluation.lines) > 1
        for index, line_eval in enumerate(evaluation.lines):
            self._cards.addWidget(
                self._line_card(index, line_eval, show_pos_summary=multiple_lines)
            )
        self._update_option_directions()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_option_directions()

    def _update_option_directions(self) -> None:
        app = QApplication.instance()
        scale = (
            app.property("fontScalePercent")
            if app is not None
            else DEFAULT_FONT_SCALE
        )
        if not isinstance(scale, int):
            scale = DEFAULT_FONT_SCALE
        breakpoint = round(
            self.OPTION_STACK_BREAKPOINT * scale / DEFAULT_FONT_SCALE
        )
        direction = (
            QBoxLayout.Direction.LeftToRight
            if self.width() >= breakpoint
            else QBoxLayout.Direction.TopToBottom
        )
        for layout in self._option_layouts:
            layout.setDirection(direction)

    def _line_card(
        self,
        index: int,
        evaluation: Evaluation,
        *,
        show_pos_summary: bool,
    ) -> QGroupBox:
        name = (
            evaluation.line.product_name if evaluation.line is not None else ""
        )
        box = QGroupBox(
            T.line_title_named(index + 1, name) if name else T.line_title(index + 1)
        )
        layout = QVBoxLayout(box)
        view = evaluation.view
        if view is None:
            text = (
                T.CARD_INCOMPLETE
                if evaluation.incomplete_only
                else T.CARD_FIX
            )
            layout.addWidget(self._note(text))  # never show stale results
            return box

        card = view.card
        pos_summary, pos_details = _pos_summary_boxes(card.pos)
        if show_pos_summary:
            layout.addWidget(pos_summary)
        layout.addWidget(section_box(card.prices))
        options = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        options.addWidget(section_box(card.website_option, role="option"), 1)
        if card.gift_option is not None:
            options.addWidget(section_box(card.gift_option, role="option"), 1)
        self._option_layouts.append(options)
        layout.addLayout(options)
        if pos_details is not None:
            layout.addWidget(pos_details)
        if view.warnings:
            layout.addWidget(
                self._note(
                    "\n".join(f"⚠ {w}" for w in view.warnings), WARNING_STYLE
                )
            )
        explain = Collapsible(T.EXPLAIN_TITLE)
        explain.set_lines(view.explanation)
        layout.addWidget(explain)
        return box


def _pos_summary_boxes(section: Section) -> tuple[QFrame, QGroupBox | None]:
    """Separate the final POS amount from its supporting calculation rows."""
    amount_labels = {T.LBL_POS_AMOUNT, T.LBL_TOTAL_POS}
    amount = next(
        (row for row in section.rows if row.label in amount_labels),
        section.rows[0] if section.rows else None,
    )
    hero = QFrame()
    hero.setObjectName("posHero")
    hero.setFrameShape(QFrame.Shape.StyledPanel)
    hero.setMinimumHeight(104)
    hero_layout = QVBoxLayout(hero)
    caption = QLabel(section.title)
    caption.setObjectName("posCaption")
    hero_layout.addWidget(caption)
    if amount is not None:
        value = QLabel(amount.value)
        value.setObjectName("posAmount")
        value.setWordWrap(True)
        value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        is_amount = amount.label in amount_labels
        is_missing = amount.value == T.NOT_AVAILABLE or amount.value.startswith(
            f"{T.NOT_AVAILABLE}:"
        )
        value.setProperty("missing", not is_amount or is_missing)
        if amount.tooltip:
            value.setToolTip(amount.tooltip)
        hero_layout.addWidget(value)

    details_rows = tuple(
        row for row in section.rows if row is not amount
    )
    details = (
        None
        if not details_rows and section.note is None
        else section_box(
            Section(T.SEC_POS_DETAILS, details_rows, section.note)
        )
    )
    return hero, details


class CalculatorTab(QWidget):
    """Controller: rows -> LineForms -> evaluate_transaction -> render."""

    save_requested = Signal(
        object
    )  # TransactionEvaluation; wired to history in M5

    def __init__(
        self, repo: ProductRepository, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._repo = repo
        self._products: list[Product] = repo.search()
        self._bulk = (
            False  # suppress recalculation while all rows are updated at once
        )
        self.rows: list[LineRow] = []
        self.evaluation = TransactionEvaluation(lines=())

        self.panel = TransactionPanel()
        self.add_button = QPushButton(T.BTN_ADD_LINE)
        self.save_button = QPushButton(T.BTN_SAVE_CALCULATION)
        self.save_button.setEnabled(False)

        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.addStretch(
            1
        )  # rows are inserted before this stretch
        rows_scroll = QScrollArea()
        rows_scroll.setWidgetResizable(True)
        rows_scroll.setWidget(self._rows_host)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(rows_scroll, 1)
        left_layout.addWidget(self.add_button)

        results_scroll = QScrollArea()
        results_scroll.setWidgetResizable(True)
        results_scroll.setWidget(self.panel)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(results_scroll, 1)
        right_layout.addWidget(self.save_button)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        self._splitter = splitter
        self.set_font_scale(DEFAULT_FONT_SCALE)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self.add_button.clicked.connect(lambda _c=False: self.add_line())
        self.save_button.clicked.connect(
            lambda _c=False: self.save_requested.emit(self.evaluation)
        )
        self.add_line()

    # ---- rows ------------------------------------------------------------

    def add_line(self) -> LineRow:
        row = LineRow()
        row.line.set_products(
            self._products
        )  # not connected yet: no recalculation
        row.line.changed.connect(self.recalculate)
        row.move_up.connect(lambda r: self._move(r, -1))
        row.move_down.connect(lambda r: self._move(r, +1))
        row.remove_requested.connect(self.remove_line)
        self.rows.append(row)
        self._rows_layout.insertWidget(len(self.rows) - 1, row)
        self._renumber()
        self.recalculate()
        return row

    def remove_line(self, row: LineRow) -> None:
        if len(self.rows) <= 1 or row not in self.rows:
            return  # at least one line always stays
        self.rows.remove(row)
        self._rows_layout.removeWidget(row)
        row.hide()
        row.setParent(None)
        row.deleteLater()
        self._renumber()
        self.recalculate()

    def _move(self, row: LineRow, delta: int) -> None:
        i = self.rows.index(row)
        j = i + delta
        if not 0 <= j < len(self.rows):
            return
        # The widget itself moves, so all of its entered state moves with it.
        self.rows[i], self.rows[j] = self.rows[j], self.rows[i]
        self._rows_layout.removeWidget(row)
        self._rows_layout.insertWidget(j, row)
        self._renumber()
        self.recalculate()

    def _renumber(self) -> None:
        for index, row in enumerate(self.rows):
            row.set_position(index, len(self.rows))

    # ---- data ------------------------------------------------------------

    def refresh_products(self) -> None:
        self._products = self._repo.search()
        self._bulk = True
        try:
            for row in self.rows:
                row.line.set_products(self._products)
        finally:
            self._bulk = False
        self.recalculate()

    def set_font_scale(self, percent: int) -> None:
        """Give the input pane more room as text grows."""
        left_ratio = max(0.40, min(0.48, 0.43 + (percent - 120) / 1000))
        self._splitter.setSizes(
            [round(1000 * left_ratio), round(1000 * (1 - left_ratio))]
        )

    def recalculate(self) -> None:
        if self._bulk:
            return
        evaluation = evaluate_transaction(
            [row.line.form() for row in self.rows]
        )
        self.evaluation = evaluation
        for row, line_eval in zip(self.rows, evaluation.lines, strict=True):
            row.line.set_feedback(line_eval.errors, line_eval.hints)
        self.panel.show_evaluation(evaluation)
        self.save_button.setEnabled(evaluation.valid)
