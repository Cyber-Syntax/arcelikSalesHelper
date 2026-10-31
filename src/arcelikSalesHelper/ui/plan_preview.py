"""Shared plan preview: CSV import and the web update render a plan here."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.domain.formatting import format_try
from arcelikSalesHelper.infrastructure.csv_import import (
    Decision,
    ImportPlan,
    Kind,
    PlanItem,
)

from .common import ERROR_STYLE

CellsFn = Callable[[PlanItem], Sequence[str]]

STATUS = {
    Kind.NEW: T.STATUS_NEW,
    Kind.CONFLICT: T.STATUS_CONFLICT,
    Kind.STOCK_UPDATE: T.STATUS_STOCK_UPDATE,
    Kind.UNCHANGED: T.STATUS_UNCHANGED,
}


def price_text(value: Decimal | None, *, website: bool) -> str:
    """0 = unknown regular price (—) or no website discount (YOK)."""
    if value is None:
        return ""
    if value == 0:
        return T.NO_WEBSITE_DISCOUNT if website else T.NO_PRICE
    return format_try(value)


def scrape_cells(item: PlanItem) -> tuple[str, ...]:
    """Columns of ``UPDATE_PREVIEW_COLUMNS``; the decision column stays empty."""
    row, existing = item.row, item.existing
    name = existing.name if existing is not None else row.name
    if item.restores:
        name += T.ARCHIVED_SUFFIX
    old_regular = None if existing is None else existing.regular_price
    old_website = None if existing is None else existing.website_price
    return (
        name,
        STATUS[item.kind],
        price_text(old_regular, website=False),
        price_text(row.regular_price, website=False),
        price_text(old_website, website=True),
        price_text(row.website_price, website=True),
        "",
        "; ".join(row.warnings),
    )


def _readonly_table(columns: Sequence[str]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(list(columns))
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().hide()
    table.horizontalHeader().setStretchLastSection(True)
    return table


class PlanPreviewWidget(QWidget):
    """Preview table, per-row decisions, bulk actions and the row-error list.

    ``default_conflict=None`` forces an explicit choice for every conflict
    (CSV import). ``choose_new=True`` gives NEW rows an Ekle/Atla choice.
    """

    changed = Signal()

    def __init__(
        self,
        columns: Sequence[str],
        cells: CellsFn,
        decision_column: int,
        *,
        default_conflict: Decision | None = None,
        choose_new: bool = False,
        fix_message: str = T.IMPORT_FIX_FILE,
        nothing_message: str = T.IMPORT_NOTHING,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cells = cells
        self._decision_column = decision_column
        self._default_conflict = default_conflict
        self._choose_new = choose_new
        self._fix_message = fix_message
        self._nothing_message = nothing_message
        self.plan: ImportPlan | None = None
        self.decision_combos: dict[int, QComboBox] = {}  # CSV row -> combo
        self.new_combos: dict[int, QComboBox] = {}

        self.counts_label = QLabel()
        self.counts_label.setWordWrap(True)
        self.table = _readonly_table(columns)
        self.update_all_button = QPushButton(T.UPDATE_APPLY_ALL)
        self.skip_all_button = QPushButton(T.UPDATE_SKIP_ALL)
        self.skip_new_button = QPushButton(T.UPDATE_SKIP_NEW)
        self.add_new_button = QPushButton(T.UPDATE_ADD_NEW)
        self.errors_label = QLabel(T.LBL_ROWS_WITH_ERRORS)
        self.errors_label.setStyleSheet(ERROR_STYLE)
        self.errors_table = _readonly_table(T.IMPORT_ERROR_COLUMNS)
        self.errors_table.setMaximumHeight(160)
        self.valid_only_check = QCheckBox(T.CHK_VALID_ONLY)

        bulk = QHBoxLayout()
        for button in (
            self.update_all_button,
            self.skip_all_button,
            self.skip_new_button,
            self.add_new_button,
        ):
            bulk.addWidget(button)
        bulk.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.counts_label)
        layout.addLayout(bulk)
        layout.addWidget(self.table, 3)
        layout.addWidget(self.errors_label)
        layout.addWidget(self.errors_table, 1)
        layout.addWidget(self.valid_only_check)

        self.update_all_button.clicked.connect(
            lambda _c=False: self._set_all(
                self.decision_combos, Decision.UPDATE
            )
        )
        self.skip_all_button.clicked.connect(
            lambda _c=False: self._set_all(self.decision_combos, Decision.SKIP)
        )
        self.skip_new_button.clicked.connect(
            lambda _c=False: self._set_all(self.new_combos, Decision.SKIP)
        )
        self.add_new_button.clicked.connect(
            lambda _c=False: self._set_all(self.new_combos, Decision.UPDATE)
        )
        self.valid_only_check.toggled.connect(lambda _c: self.changed.emit())
        self.clear()

    # ---- content ---------------------------------------------------------

    def clear(self) -> None:
        self.plan = None
        self.decision_combos.clear()
        self.new_combos.clear()
        self.table.setRowCount(0)
        self.errors_table.setRowCount(0)
        self.counts_label.setText("")
        blocker = QSignalBlocker(self.valid_only_check)
        self.valid_only_check.setChecked(False)
        blocker.unblock()
        self._update_chrome()

    def set_plan(self, plan: ImportPlan, counts_text: str) -> None:
        self.clear()
        self.plan = plan
        self.counts_label.setText(counts_text)
        self.table.setRowCount(len(plan.items))
        for r, item in enumerate(plan.items):
            self._fill_row(r, item)
        self.table.resizeColumnsToContents()
        if plan.errors:
            self.errors_table.setRowCount(len(plan.errors))
            for r, err in enumerate(plan.errors):
                for c, text in enumerate(
                    (str(err.row), err.column or "", err.message)
                ):
                    self.errors_table.setItem(r, c, QTableWidgetItem(text))
        self._update_chrome()

    def _combo_for(self, item: PlanItem) -> QComboBox | None:
        combo = QComboBox()
        if item.kind is Kind.CONFLICT:
            if self._default_conflict is None:
                combo.addItem(T.COMBO_CHOOSE, None)
            combo.addItem(
                T.COMBO_UPDATE_RESTORE if item.restores else T.COMBO_UPDATE,
                Decision.UPDATE,
            )
            combo.addItem(T.COMBO_SKIP, Decision.SKIP)
            if self._default_conflict is not None:
                combo.setCurrentIndex(combo.findData(self._default_conflict))
            self.decision_combos[item.row.row] = combo
        elif item.kind is Kind.NEW and self._choose_new:
            combo.addItem(T.COMBO_ADD, Decision.UPDATE)
            combo.addItem(T.COMBO_SKIP, Decision.SKIP)
            self.new_combos[item.row.row] = combo
        else:
            return None
        combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
        return combo

    def _fill_row(self, r: int, item: PlanItem) -> None:
        combo = self._combo_for(item)
        for c, text in enumerate(self._cells(item)):
            if c == self._decision_column and combo is not None:
                continue
            cell = QTableWidgetItem(text)
            if text:
                cell.setToolTip(text)
            self.table.setItem(r, c, cell)
        if combo is not None:
            self.table.setCellWidget(r, self._decision_column, combo)

    def _update_chrome(self) -> None:
        plan = self.plan
        has_errors = plan is not None and bool(plan.errors)
        self.errors_label.setVisible(has_errors)
        self.errors_table.setVisible(has_errors)
        self.valid_only_check.setVisible(has_errors)
        self.update_all_button.setVisible(bool(self.decision_combos))
        self.skip_all_button.setVisible(bool(self.decision_combos))
        self.skip_new_button.setVisible(bool(self.new_combos))
        self.add_new_button.setVisible(bool(self.new_combos))

    def _set_all(
        self, combos: dict[int, QComboBox], decision: Decision
    ) -> None:
        for combo in combos.values():
            blocker = QSignalBlocker(combo)
            index = combo.findData(decision)
            if index >= 0:
                combo.setCurrentIndex(index)
            blocker.unblock()
        self.changed.emit()

    # ---- state -----------------------------------------------------------

    def decisions(self) -> dict[int, Decision]:
        out: dict[int, Decision] = {}
        for row, combo in self.decision_combos.items():
            data = combo.currentData()
            if isinstance(data, Decision):
                out[row] = data
        return out

    def new_skipped(self) -> set[int]:
        return {
            row
            for row, combo in self.new_combos.items()
            if combo.currentData() is Decision.SKIP
        }

    def valid_only(self) -> bool:
        return self.valid_only_check.isChecked()

    def _has_effect(self, plan: ImportPlan) -> bool:
        if not self._choose_new:
            return plan.actionable
        decisions = self.decisions()
        skipped = self.new_skipped()
        for item in plan.items:
            if item.kind is Kind.NEW and item.row.row not in skipped:
                return True
            if item.kind is Kind.STOCK_UPDATE:
                return True
            if (
                item.kind is Kind.CONFLICT
                and decisions.get(item.row.row) is Decision.UPDATE
            ):
                return True
        return False

    def blocking_reason(self) -> str | None:
        """None = ready to apply; "" = no plan loaded; otherwise the reason."""
        plan = self.plan
        if plan is None:
            return ""
        if plan.errors and not self.valid_only_check.isChecked():
            return self._fix_message
        if len(self.decisions()) < len(plan.conflicts):
            return T.IMPORT_DECIDE_ALL
        if not self._has_effect(plan):
            return self._nothing_message
        return None
