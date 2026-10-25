from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from arcelikSalesHelper.application.history import (
    SnapshotHeader,
    StoredLine,
    StoredSnapshot,
    confirmation_text,
    parse_snapshot,
    summarize,
)
from arcelikSalesHelper.domain.result import Err, Ok
from arcelikSalesHelper.infrastructure.history_repository import (
    HistoryRepository,
)

from .calculator_tab import Collapsible, section_box
from .common import HINT_STYLE, WARNING_STYLE, format_local_timestamp

_COLUMNS = ("Saved at", "Products", "Lines", "POS-entry total (verify)")


class SnapshotDetail(QWidget):
    """Renders a StoredSnapshot. Everything shown is a stored string."""

    def __init__(
        self, snapshot: StoredSnapshot, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        header = QLabel(
            f"Saved calculation #{snapshot.id}\n"
            f"Saved {format_local_timestamp(snapshot.created_at)} · "
            f"app {snapshot.app_version} · schema {snapshot.schema_version}"
        )
        header.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(header)
        layout.addWidget(
            self._note(
                confirmation_text(snapshot.confirmation_state), WARNING_STYLE
            )
        )
        layout.addWidget(
            self._note(
                "Shown exactly as calculated and saved. Later changes to products, prices "
                "or gifts do not affect it."
            )
        )
        for line in snapshot.lines:
            layout.addWidget(self._line_box(line))
        for section in snapshot.totals_sections:
            layout.addWidget(section_box(section))
        layout.addStretch(1)

    @staticmethod
    def _note(text: str, style: str = HINT_STYLE) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(style)
        return label

    def _line_box(self, line: StoredLine) -> QGroupBox:
        box = QGroupBox(f"Line {line.line_index + 1}: {line.product_name}")
        layout = QVBoxLayout(box)
        layout.addWidget(section_box(line.entered))
        layout.addWidget(section_box(line.prices))
        options = QHBoxLayout()  # same weight for both: no option is favoured
        options.addWidget(section_box(line.website_option), 1)
        if line.gift_option is not None:
            options.addWidget(section_box(line.gift_option), 1)
        layout.addLayout(options)
        layout.addWidget(section_box(line.pos))
        if line.warnings:
            layout.addWidget(
                self._note(
                    "\n".join(f"⚠ {w}" for w in line.warnings), WARNING_STYLE
                )
            )
        explain = Collapsible("How this was calculated")
        explain.set_lines(line.explanation)
        layout.addWidget(explain)
        return box


class HistoryTab(QWidget):
    """Read-only list of saved calculations. No edit, no delete."""

    def __init__(
        self,
        repo: HistoryRepository,
        page_size: int = 100,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repo = repo
        self._page_size = page_size
        self._oldest_id: int | None = None
        self._more = False

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.count_label = QLabel()
        self.count_label.setStyleSheet(HINT_STYLE)
        self.load_more_button = QPushButton("Load older calculations")
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.table, 1)
        left_layout.addWidget(self.count_label)
        left_layout.addWidget(self.load_more_button)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.detail_scroll)
        splitter.setSizes([480, 620])
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self.table.itemSelectionChanged.connect(self._show_selected)
        self.load_more_button.clicked.connect(
            lambda _c=False: self._load_more()
        )
        self.reload()

    # ---- list ------------------------------------------------------------

    def selected_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        data = (
            item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        )
        return data if isinstance(data, int) else None

    def reload(self, select_id: int | None = None) -> None:
        keep = select_id if select_id is not None else self.selected_id()
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            self._oldest_id = None
            self._append(self._repo.list_headers(self._page_size))
            if keep is not None:
                for row in range(self.table.rowCount()):
                    item = self.table.item(row, 0)
                    if (
                        item is not None
                        and item.data(Qt.ItemDataRole.UserRole) == keep
                    ):
                        self.table.selectRow(row)
                        break
        finally:
            self.table.blockSignals(False)
        self._update_footer()
        self._show_selected()

    def _load_more(self) -> None:
        self._append(
            self._repo.list_headers(self._page_size, before_id=self._oldest_id)
        )
        self._update_footer()

    def _append(self, headers: list[SnapshotHeader]) -> None:
        for header in headers:
            summary = summarize(header)
            row = self.table.rowCount()
            self.table.insertRow(row)
            cells = (
                format_local_timestamp(summary.created_at),
                summary.products_text,
                str(summary.line_count),
                summary.pos_total,
            )
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, summary.id)
                self.table.setItem(row, col, item)
        if headers:
            self._oldest_id = headers[-1].id
        self._more = len(headers) == self._page_size

    def _update_footer(self) -> None:
        total = self._repo.count()
        shown = self.table.rowCount()
        self.count_label.setText(
            f"Showing {shown} of {total} saved calculations"
            if total
            else "No saved calculations yet."
        )
        self.load_more_button.setEnabled(self._more)

    # ---- detail ----------------------------------------------------------

    def _show_message(self, text: str) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(HINT_STYLE)
        self.detail_scroll.setWidget(
            label
        )  # the scroll area deletes the previous widget

    def _show_selected(self) -> None:
        snapshot_id = self.selected_id()
        if snapshot_id is None:
            self._show_message(
                "Select a saved calculation to see its details."
            )
            return
        record = self._repo.get(snapshot_id)
        if record is None:
            self._show_message("This calculation no longer exists.")
            return
        match parse_snapshot(record):
            case Ok(snapshot):
                self.detail_scroll.setWidget(SnapshotDetail(snapshot))
            case Err(message):
                self._show_message(message)
