from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from arcelikSalesHelper.domain.formatting import format_try
from arcelikSalesHelper.domain.result import Err, Ok
from arcelikSalesHelper.infrastructure.backups import (
    BackupManager,
    BackupReason,
)
from arcelikSalesHelper.infrastructure.csv_import import (
    Decision,
    ImportFormat,
    ImportPlan,
    ImportSummary,
    Kind,
    PlanItem,
    apply_plan,
    index_products,
    parse_csv_file,
    plan_import,
)
from arcelikSalesHelper.infrastructure.repositories import ProductRepository

from .common import ERROR_STYLE, HINT_STYLE

_COLUMNS = (
    "Row",
    "Status",
    "Product",
    "Regular price",
    "Website price",
    "Quantity",
    "Decision / notes",
)
_DECISION_COLUMN = 6
_STATUS = {
    Kind.NEW: "New",
    Kind.CONFLICT: "Conflict",
    Kind.STOCK_UPDATE: "Stock update",
    Kind.UNCHANGED: "Unchanged",
}
_FORMAT_TEXT = {
    ImportFormat.PRICES: "Price list (quantity column optional)",
    ImportFormat.STOCK: "Stock counts (never creates products)",
}


def _price_text(old: Decimal | None, new: Decimal | None) -> str:
    if new is None:
        return ""
    if old is None or old == new:
        return format_try(new)
    return f"{format_try(old)} → {format_try(new)}"


def _quantity_text(old: int | None, new: int | None) -> str:
    if new is None:
        return ""
    if old == new:
        return str(new)
    return f"{'—' if old is None else old} → {new}"


class ImportDialog(QDialog):
    imported = Signal()

    def __init__(
        self,
        repo: ProductRepository,
        conn: sqlite3.Connection,
        backups: BackupManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repo = repo
        self._conn = conn
        self._backups = backups
        self._path: Path | None = None
        self.plan: ImportPlan | None = None
        self.summary: ImportSummary | None = None
        self.decision_combos: dict[
            int, QComboBox
        ] = {}  # keyed by CSV row number

        self.setWindowTitle("Import CSV")
        self.resize(980, 620)

        self.choose_button = QPushButton("Choose CSV file…")
        self.path_label = QLabel("No file chosen.")
        self.path_label.setStyleSheet(HINT_STYLE)
        self.file_error = QLabel()
        self.file_error.setStyleSheet(ERROR_STYLE)
        self.file_error.setWordWrap(True)
        self.file_error.hide()
        self.counts_label = QLabel()
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.errors_label = QLabel("Rows with errors")
        self.errors_label.setStyleSheet(ERROR_STYLE)
        self.errors_table = QTableWidget(0, 3)
        self.errors_table.setHorizontalHeaderLabels(
            ["Row", "Column", "Problem"]
        )
        self.errors_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.errors_table.verticalHeader().hide()
        self.errors_table.horizontalHeader().setStretchLastSection(True)
        self.errors_table.setMaximumHeight(160)
        self.valid_only_check = QCheckBox(
            "Import the valid rows only (leave rows with errors out)"
        )
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(HINT_STYLE)
        self.apply_button = QPushButton("Apply import")
        self.apply_button.setEnabled(False)
        self.close_button = QPushButton("Close")

        top = QHBoxLayout()
        top.addWidget(self.choose_button)
        top.addWidget(self.path_label, 1)
        bottom = QHBoxLayout()
        bottom.addWidget(self.status_label, 1)
        bottom.addWidget(self.apply_button)
        bottom.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.file_error)
        layout.addWidget(self.counts_label)
        layout.addWidget(self.table, 3)
        layout.addWidget(self.errors_label)
        layout.addWidget(self.errors_table, 1)
        layout.addWidget(self.valid_only_check)
        layout.addLayout(bottom)
        self._set_error_widgets_visible(False)

        self.choose_button.clicked.connect(lambda _c=False: self.choose_file())
        self.apply_button.clicked.connect(lambda _c=False: self._apply())
        self.close_button.clicked.connect(self.reject)
        self.valid_only_check.toggled.connect(lambda _c: self._update_apply())

    # ---- loading ---------------------------------------------------------

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a CSV file", "", "CSV files (*.csv);;All files (*)"
        )
        if path:
            self.load_file(Path(path))

    def load_file(self, path: Path) -> None:
        self._reset()
        self._path = path
        self.path_label.setText(str(path))
        parsed = parse_csv_file(path)
        if isinstance(parsed, Err):
            self.file_error.setText(parsed.error)
            self.file_error.show()
            self._update_apply()
            return
        existing = index_products(self._repo.search("", include_archived=True))
        self.plan = plan_import(parsed.value, existing)
        self._show_plan(self.plan, _FORMAT_TEXT[parsed.value.format])
        self._update_apply()

    def _reset(self) -> None:
        self.plan = None
        self.decision_combos.clear()
        self.table.setRowCount(0)
        self.errors_table.setRowCount(0)
        self.file_error.hide()
        self.counts_label.setText("")
        self.valid_only_check.setChecked(False)
        self._set_error_widgets_visible(False)

    def _set_error_widgets_visible(self, visible: bool) -> None:
        self.errors_label.setVisible(visible)
        self.errors_table.setVisible(visible)
        self.valid_only_check.setVisible(visible)

    def _show_plan(self, plan: ImportPlan, format_text: str) -> None:
        self.table.setRowCount(len(plan.items))
        for r, item in enumerate(plan.items):
            self._fill_row(r, item)
        n = {
            kind: sum(1 for i in plan.items if i.kind is kind) for kind in Kind
        }
        self.counts_label.setText(
            f"{format_text}: {n[Kind.NEW]} new · {n[Kind.CONFLICT]} conflicts (decide each) · "
            f"{n[Kind.STOCK_UPDATE]} quantity updates · {n[Kind.UNCHANGED]} unchanged · "
            f"{len(plan.errors)} rows with errors"
        )
        self.table.resizeColumnsToContents()
        if plan.errors:
            self.errors_table.setRowCount(len(plan.errors))
            for r, err in enumerate(plan.errors):
                for c, text in enumerate(
                    (str(err.row), err.column or "", err.message)
                ):
                    self.errors_table.setItem(r, c, QTableWidgetItem(text))
            self._set_error_widgets_visible(True)

    def _fill_row(self, r: int, item: PlanItem) -> None:
        row, existing = item.row, item.existing
        name = row.name + (" (archived)" if item.restores else "")
        cells = (
            str(row.row),
            _STATUS[item.kind],
            name,
            _price_text(
                None if existing is None else existing.regular_price,
                row.regular_price,
            ),
            _price_text(
                None if existing is None else existing.website_price,
                row.website_price,
            ),
            _quantity_text(
                None if existing is None else existing.quantity, row.quantity
            ),
        )
        for c, text in enumerate(cells):
            self.table.setItem(r, c, QTableWidgetItem(text))
        if item.kind is Kind.CONFLICT:
            combo = QComboBox()
            combo.addItem("Choose…", None)
            combo.addItem(
                "Update and restore" if item.restores else "Update",
                Decision.UPDATE,
            )
            combo.addItem("Skip", Decision.SKIP)
            combo.currentIndexChanged.connect(lambda _i: self._update_apply())
            self.decision_combos[row.row] = combo
            self.table.setCellWidget(r, _DECISION_COLUMN, combo)
        else:
            self.table.setItem(
                r, _DECISION_COLUMN, QTableWidgetItem("; ".join(row.warnings))
            )

    # ---- applying --------------------------------------------------------

    def decisions(self) -> dict[int, Decision]:
        out: dict[int, Decision] = {}
        for row, combo in self.decision_combos.items():
            data = combo.currentData()
            if isinstance(data, Decision):
                out[row] = data
        return out

    def _update_apply(self) -> None:
        plan = self.plan
        if plan is None:
            self.apply_button.setEnabled(False)
            self.status_label.setText("")
            return
        reason: str | None = None
        if plan.errors and not self.valid_only_check.isChecked():
            reason = "Fix the file, or tick “Import the valid rows only”."
        elif len(self.decisions()) < len(plan.conflicts):
            reason = "Choose Update or Skip for every conflict."
        elif not plan.actionable:
            reason = "Nothing to import."
        self.status_label.setText(
            reason or "Ready. A backup is made before the import is applied."
        )
        self.apply_button.setEnabled(reason is None)

    def _apply(self) -> None:
        plan = self.plan
        if plan is None:
            return
        if self._backups is not None:
            outcome = self._backups.run(BackupReason.PRE_IMPORT)
            if isinstance(outcome, Err):
                answer = QMessageBox.question(
                    self,
                    "Backup failed",
                    f"{outcome.error.message}\n\nImport without a fresh backup?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
        note = None if self._path is None else f"csv: {self._path.name}"
        result = apply_plan(
            self._conn,
            plan,
            self.decisions(),
            import_valid_only=self.valid_only_check.isChecked(),
            note=note,
        )
        match result:
            case Err(failure):
                QMessageBox.critical(self, "Import failed", failure.message)
            case Ok(summary):
                self.summary = summary
                QMessageBox.information(
                    self, "Import complete", "\n".join(summary.lines())
                )
                self.imported.emit()
                self.accept()
