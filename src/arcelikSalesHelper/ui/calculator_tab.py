from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSignalBlocker, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QResizeEvent
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
    QListWidget,
    QListWidgetItem,
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
from arcelikSalesHelper.domain.models import (
    POS_LABEL,
    ManagerMode,
    PosCalculationMode,
)
from arcelikSalesHelper.domain.products import Product
from arcelikSalesHelper.infrastructure.repositories import ProductRepository

from .common import HINT_STYLE, WARNING_STYLE, FieldBlock
from .theme import DEFAULT_FONT_SCALE


class CalculatorLineWidget(QWidget):
    """Inputs of one calculator line. Holds no formulas; emits ``changed``.

    M4 reuses this class once per line.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._updating = False
        self._product: Product | None = None
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
        self.pos_mode_combo = QComboBox()
        self.pos_mode_combo.addItem(
            T.POS_MODE_FIXED, PosCalculationMode.FIXED_AMOUNT
        )
        self.pos_mode_combo.addItem(
            T.POS_MODE_PERCENTAGE, PosCalculationMode.PERCENTAGE
        )

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
        form.addRow(T.FORM_POS_CALCULATION_MODE, self.pos_mode_combo)

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
        self.pos_mode_combo.currentIndexChanged.connect(self._emit)

    # ---- state -----------------------------------------------------------

    def _emit(self, *_args: object) -> None:
        if not self._updating:
            self.changed.emit()

    def selected_product(self) -> Product | None:
        return self._product

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
            pos_calculation_mode=(
                self.pos_mode_combo.currentData()
                if isinstance(
                    self.pos_mode_combo.currentData(), PosCalculationMode
                )
                else PosCalculationMode.FIXED_AMOUNT
            ),
            product_id=None if product is None else product.id,
        )

    def set_product(self, product: Product) -> None:
        """Copy a saved product into this line; never link editable values."""
        self._updating = True
        try:
            self._product = product
            self.name_edit.setText(product.name)
            self.regular_edit.setText(format_money_input(product.regular_price))
            self.website_edit.setText(format_money_input(product.website_price))
            self.gift_name_edit.setText(product.default_gift_name or "")
            self.name_edit.setReadOnly(True)
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
        if row.label == T.LBL_DISCOUNT_AMOUNT:
            label.setObjectName("discountAmountLabel")
            value.setObjectName("discountAmountValue")
        if role == "line-prices" and row.label == T.LBL_QUANTITY:
            label.setObjectName("lineQuantityLabel")
            value.setObjectName("lineQuantityValue")
        value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        if row.label in (
            T.LBL_WEBSITE_OFFER_TOTAL,
            T.LBL_FIRST_PRICE_TEN_PERCENT,
            T.LBL_MANAGER_LINE_TOTAL,
        ):
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
                    self._totals.addWidget(_pos_summary_box(section))
                else:
                    self._totals.addWidget(section_box(section))
        elif evaluation.pending_reason:
            self._totals.addWidget(self._note(evaluation.pending_reason))
        for index, line_eval in enumerate(evaluation.lines):
            self._cards.addWidget(self._line_card(index, line_eval))
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
    ) -> QGroupBox:
        name = (
            evaluation.line.product_name if evaluation.line is not None else ""
        )
        box = QGroupBox(
            T.line_title_named(index + 1, name) if name else T.line_title(index + 1)
        )
        box.setObjectName("lineResultCard")
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
        layout.addWidget(_pos_summary_box(card.pos))
        layout.addWidget(section_box(card.prices, role="line-prices"))
        options = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        options.addWidget(section_box(card.website_option, role="option"), 1)
        if card.gift_option is not None:
            options.addWidget(section_box(card.gift_option, role="option"), 1)
        self._option_layouts.append(options)
        layout.addLayout(options)
        if view.warnings:
            layout.addWidget(
                self._note(
                    "\n".join(f"⚠ {w}" for w in view.warnings), WARNING_STYLE
                )
            )
        return box


def _pos_summary_box(section: Section) -> QFrame:
    """Render the final POS amount as the section's prominent result."""
    amount_labels = {T.LBL_POS_AMOUNT, T.LBL_TOTAL_POS}
    amount = next(
        (row for row in section.rows if row.label in amount_labels),
        section.rows[0] if section.rows else None,
    )
    hero = QFrame()
    hero.setObjectName("posHero")
    hero.setFrameShape(QFrame.Shape.StyledPanel)
    hero.setMinimumHeight(58)
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

    return hero


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
        self._bulk = (
            False  # suppress recalculation while all rows are updated at once
        )
        self.rows: list[LineRow] = []
        self.evaluation = TransactionEvaluation(lines=())

        self.panel = TransactionPanel()
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText(T.PH_CALCULATOR_PRODUCT_SEARCH)
        self.product_search.setClearButtonEnabled(True)
        self.product_list = QListWidget()
        self.product_list.setObjectName("calculatorProductList")
        self.product_list.setMaximumHeight(150)
        self.product_list.setSelectionMode(
            QListWidget.SelectionMode.NoSelection
        )
        self.product_list.setSpacing(3)
        self.product_list.setStyleSheet(
            "QListWidget#calculatorProductList {"
            " background-color: #f8fafc; color: #26384a; }"
            "QListWidget#calculatorProductList::indicator {"
            " width: 20px; height: 20px; border: 2px solid #52677d;"
            " border-radius: 3px; background-color: #ffffff; }"
            "QListWidget#calculatorProductList::indicator:checked {"
            " background-color: #1769aa; border-color: #104d80; }"
            "QListWidget#calculatorProductList::indicator:unchecked:hover {"
            " border-color: #1769aa; }"
            "QListWidget#calculatorProductList::item {"
            " padding: 5px; color: #26384a; }"
        )
        self.selection_count = QLabel(T.calculator_selection_count(0))
        self.add_selected_button = QPushButton(T.BTN_ADD_SELECTED_PRODUCTS)
        self.add_selected_button.setEnabled(False)
        self.add_one_off_button = QPushButton(T.BTN_ADD_ONE_OFF_LINE)
        self.save_button = QPushButton(T.BTN_SAVE_CALCULATION)
        self.save_button.setEnabled(False)
        self._staged_products: dict[int, Product] = {}
        self._updating_product_list = False
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._render_products)

        selector = QGroupBox(T.CALCULATOR_PRODUCT_SELECTOR)
        selector_layout = QVBoxLayout(selector)
        selector_layout.addWidget(self.product_search)
        selector_layout.addWidget(self.product_list)
        selector_actions = QHBoxLayout()
        selector_actions.addWidget(self.selection_count, 1)
        selector_actions.addWidget(self.add_one_off_button)
        selector_actions.addWidget(self.add_selected_button)
        selector_layout.addLayout(selector_actions)

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
        left_layout.addWidget(selector)
        left_layout.addWidget(rows_scroll, 1)

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

        self.product_search.textChanged.connect(
            lambda _text: self._search_timer.start()
        )
        self.product_search.returnPressed.connect(self._search_now)
        self.product_list.itemChanged.connect(self._on_product_check_changed)
        self.add_selected_button.clicked.connect(
            lambda _c=False: self.add_selected_products()
        )
        self.add_one_off_button.clicked.connect(
            lambda _c=False: self.add_one_off_line()
        )
        self.save_button.clicked.connect(
            lambda _c=False: self.save_requested.emit(self.evaluation)
        )
        self._render_products()
        self.add_line()

    # ---- rows ------------------------------------------------------------

    def add_line(self, product: Product | None = None) -> LineRow:
        """Append a one-off line or a line copied from a saved product."""
        # The initial blank row becomes the first selected product line, so a
        # batch add never leaves an accidental incomplete line behind.
        if product is not None and len(self.rows) == 1:
            starter = self.rows[0]
            if self._is_empty_line(starter.line):
                starter.line.set_product(product)
                if not self._bulk:
                    self.recalculate()
                return starter
        row = LineRow()
        if product is not None:
            row.line.set_product(product)
        row.line.changed.connect(self.recalculate)
        row.move_up.connect(lambda r: self._move(r, -1))
        row.move_down.connect(lambda r: self._move(r, +1))
        row.remove_requested.connect(self.remove_line)
        self.rows.append(row)
        self._rows_layout.insertWidget(len(self.rows) - 1, row)
        self._renumber()
        self.recalculate()
        return row

    @staticmethod
    def _is_empty_line(line: CalculatorLineWidget) -> bool:
        return (
            not line.name_edit.text()
            and not line.regular_edit.text()
            and not line.website_edit.text()
            and not line.gift_name_edit.text()
            and not line.manager_edit.text()
            and line.quantity_spin.value() == 1
            and not line.gift_check.isChecked()
        )

    def add_one_off_line(self) -> LineRow:
        """Focus the starter line or append a new editable one-off line."""
        if len(self.rows) == 1 and self._is_empty_line(self.rows[0].line):
            row = self.rows[0]
            row.line.name_edit.setFocus()
            return row
        row = self.add_line()
        row.line.name_edit.setFocus()
        return row

    def add_selected_products(self) -> None:
        """Add checked products as lines in the order they were selected."""
        active_products = {
            product.id: product for product in self._repo.search()
        }
        products = [
            active_products[product_id]
            for product_id in self._staged_products
            if product_id in active_products
        ]
        self._staged_products = {
            product.id: product for product in products
        }
        if not products:
            self._render_products()
            return
        self._bulk = True
        try:
            for product in products:
                self.add_line(product)
            self._staged_products.clear()
            self._render_products()
        finally:
            self._bulk = False
        self.recalculate()

    def _render_products(self, _query: str | None = None) -> None:
        products = self._repo.search(self.product_search.text())
        blocker = QSignalBlocker(self.product_list)
        self.product_list.clear()
        for product in products:
            selected = product.id in self._staged_products
            item = QListWidgetItem(self._product_option_text(product, selected))
            item.setData(Qt.ItemDataRole.UserRole, product)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked
            )
            self._set_product_item_colors(item, selected)
            self.product_list.addItem(item)
        if not products:
            item = QListWidgetItem(T.CALCULATOR_NO_PRODUCTS_FOUND)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.product_list.addItem(item)
        blocker.unblock()
        count = len(self._staged_products)
        self.selection_count.setText(T.calculator_selection_count(count))
        self.add_selected_button.setEnabled(count > 0)

    @staticmethod
    def _product_option_text(product: Product, selected: bool) -> str:
        marker = "[✓]" if selected else "[ ]"
        return f"{marker}  {product.name}"

    @staticmethod
    def _set_product_item_colors(
        item: QListWidgetItem, selected: bool
    ) -> None:
        item.setBackground(
            QColor("#dceeff") if selected else QColor("#ffffff")
        )
        item.setForeground(QColor("#123653" if selected else "#26384a"))

    def _search_now(self) -> None:
        self._search_timer.stop()
        self._render_products()

    def _on_product_check_changed(self, item: QListWidgetItem) -> None:
        if self._updating_product_list:
            return
        product = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(product, Product):
            return
        selected = item.checkState() == Qt.CheckState.Checked
        if selected:
            self._staged_products[product.id] = product
        else:
            self._staged_products.pop(product.id, None)
        self._updating_product_list = True
        blocker = QSignalBlocker(self.product_list)
        item.setText(self._product_option_text(product, selected))
        self._set_product_item_colors(item, selected)
        blocker.unblock()
        self._updating_product_list = False
        count = len(self._staged_products)
        self.selection_count.setText(T.calculator_selection_count(count))
        self.add_selected_button.setEnabled(count > 0)

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
        active_products = {
            product.id: product for product in self._repo.search()
        }
        self._staged_products = {
            product_id: active_products[product_id]
            for product_id in self._staged_products
            if product_id in active_products
        }
        self._render_products()

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
