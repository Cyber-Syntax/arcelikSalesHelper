from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from arcelikSalesHelper import strings as T
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

from .common import (
    ERROR_STYLE,
    HINT_STYLE,
    ask_yes_no,
    show_critical,
    show_info,
)
from .plan_preview import STATUS, PlanPreviewWidget

_DECISION_COLUMN = 6
_FORMAT_TEXT = {
    ImportFormat.PRICES: T.FORMAT_PRICES,
    ImportFormat.STOCK: T.FORMAT_STOCK,
    ImportFormat.SCRAPE: T.FORMAT_SCRAPE,
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
    return f"{T.NONE_DASH if old is None else old} → {new}"


def _csv_cells(item: PlanItem) -> tuple[str, ...]:
    row, existing = item.row, item.existing
    return (
        str(row.row),
        STATUS[item.kind],
        row.name + (T.ARCHIVED_SUFFIX if item.restores else ""),
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
        "; ".join(row.warnings),  # replaced by the combo on conflict rows
    )


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

        self.setWindowTitle(T.IMPORT_TITLE)
        self.resize(980, 620)

        self.choose_button = QPushButton(T.BTN_CHOOSE_CSV)
        self.path_label = QLabel(T.NO_FILE_CHOSEN)
        self.path_label.setStyleSheet(HINT_STYLE)
        self.file_error = QLabel()
        self.file_error.setStyleSheet(ERROR_STYLE)
        self.file_error.setWordWrap(True)
        self.file_error.hide()
        self.preview = PlanPreviewWidget(
            T.IMPORT_COLUMNS, _csv_cells, _DECISION_COLUMN
        )
        # Members of the shared widget, kept under their historical names.
        self.counts_label = self.preview.counts_label
        self.table = self.preview.table
        self.errors_label = self.preview.errors_label
        self.errors_table = self.preview.errors_table
        self.valid_only_check = self.preview.valid_only_check
        self.decision_combos = self.preview.decision_combos
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(HINT_STYLE)
        self.apply_button = QPushButton(T.BTN_APPLY_IMPORT)
        self.apply_button.setEnabled(False)
        self.close_button = QPushButton(T.BTN_CLOSE)

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
        layout.addWidget(self.preview, 1)
        layout.addLayout(bottom)

        self.choose_button.clicked.connect(lambda _c=False: self.choose_file())
        self.apply_button.clicked.connect(lambda _c=False: self._apply())
        self.close_button.clicked.connect(self.reject)
        self.preview.changed.connect(self._update_apply)

    # ---- loading ---------------------------------------------------------

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, T.FILE_DIALOG_TITLE, "", T.FILE_DIALOG_FILTER
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
        self.show_plan(
            plan_import(parsed.value, existing),
            _FORMAT_TEXT[parsed.value.format],
        )

    def show_plan(self, plan: ImportPlan, format_text: str) -> None:
        """Preview a prebuilt plan (no file needed)."""
        self.plan = plan
        n = {
            kind: sum(1 for i in plan.items if i.kind is kind) for kind in Kind
        }
        self.preview.set_plan(
            plan,
            T.import_counts(
                format_text,
                n[Kind.NEW],
                n[Kind.CONFLICT],
                n[Kind.STOCK_UPDATE],
                n[Kind.UNCHANGED],
                len(plan.errors),
            ),
        )
        self.decision_combos = self.preview.decision_combos
        self._update_apply()

    def _reset(self) -> None:
        self.plan = None
        self.preview.clear()
        self.decision_combos = self.preview.decision_combos
        self.file_error.hide()

    # ---- applying --------------------------------------------------------

    def decisions(self) -> dict[int, Decision]:
        return self.preview.decisions()

    def _update_apply(self) -> None:
        if self.plan is None:
            self.apply_button.setEnabled(False)
            self.status_label.setText("")
            return
        reason = self.preview.blocking_reason()
        self.status_label.setText(reason or T.IMPORT_READY)
        self.apply_button.setEnabled(reason is None)

    def _apply(self) -> None:
        plan = self.plan
        if plan is None:
            return
        if self._backups is not None:
            outcome = self._backups.run(BackupReason.PRE_IMPORT)
            if isinstance(outcome, Err) and not ask_yes_no(
                self,
                T.IMPORT_BACKUP_FAILED_TITLE,
                T.import_backup_failed(outcome.error.message),
            ):
                return
        note = None if self._path is None else f"csv: {self._path.name}"
        result = apply_plan(
            self._conn,
            plan,
            self.decisions(),
            import_valid_only=self.preview.valid_only(),
            note=note,
        )
        match result:
            case Err(failure):
                show_critical(self, T.IMPORT_FAILED_TITLE, failure.message)
            case Ok(summary):
                self.summary = summary
                show_info(
                    self, T.IMPORT_DONE_TITLE, "\n".join(summary.lines())
                )
                self.imported.emit()
                self.accept()
