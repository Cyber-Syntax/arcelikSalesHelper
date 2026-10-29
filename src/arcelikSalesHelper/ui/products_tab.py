from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.application.calculator import read_money
from arcelikSalesHelper.domain.formatting import format_money_input, format_try
from arcelikSalesHelper.domain.products import Product, ProductDraft
from arcelikSalesHelper.domain.result import Err, Ok
from arcelikSalesHelper.domain.stock import StockSource, parse_quantity
from arcelikSalesHelper.infrastructure.backups import BackupManager
from arcelikSalesHelper.infrastructure.csv_export import export_products_csv
from arcelikSalesHelper.infrastructure.repositories import (
    ProductRepository,
    RepoError,
)

from .common import (
    ERROR_STYLE,
    FieldBlock,
    ask_yes_no,
    format_local_timestamp,
    localize_buttons,
    show_warning,
)
from .import_dialog import ImportDialog

_ROOT = QModelIndex()
_Index = QModelIndex | QPersistentModelIndex


class ProductTableModel(QAbstractTableModel):
    HEADERS = T.PRODUCT_HEADERS

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[Product] = []

    def set_products(self, products: list[Product]) -> None:
        self.beginResetModel()
        self._rows = list(products)
        self.endResetModel()

    def product_at(self, row: int) -> Product | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def row_of(self, product_id: int) -> int | None:
        return next(
            (i for i, p in enumerate(self._rows) if p.id == product_id), None
        )

    def rowCount(self, parent: _Index = _ROOT) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: _Index = _ROOT) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
        ):
            return self.HEADERS[section]
        return None

    def data(
        self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid():
            return None
        product = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(product, col)
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (1, 2, 6):
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.ForegroundRole and product.archived:
            return QBrush(QColor(128, 128, 128))
        if role == Qt.ItemDataRole.ToolTipRole and col == 4:
            return product.notes
        if role == Qt.ItemDataRole.ToolTipRole and col in (6, 7):
            return T.TIP_COUNTED
        return None

    @staticmethod
    def _display(product: Product, col: int) -> str:
        match col:
            case 0:
                return product.name + (
                    T.ARCHIVED_SUFFIX if product.archived else ""
                )
            case 1:
                return format_try(product.regular_price)
            case 2:
                return (
                    T.NO_WEBSITE_DISCOUNT
                    if product.website_price == 0
                    else format_try(product.website_price)
                )
            case 3:
                return product.default_gift_name or ""
            case 4:
                return " ".join((product.notes or "").split())
            case 5:
                return format_local_timestamp(product.updated_at)
            case 6:
                return (
                    "—"
                    if product.quantity is None
                    else f"{product.quantity:,}".replace(",", ".")
                )
            case _:
                return (
                    ""
                    if product.quantity_updated_at is None
                    else format_local_timestamp(product.quantity_updated_at)
                )


class ProductDialog(QDialog):
    """Add / edit dialog. Errors are shown inline; the dialog stays open on failure."""

    def __init__(
        self,
        repo: ProductRepository,
        product: Product | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repo = repo
        self._product = product
        self.saved: Product | None = None
        self.setWindowTitle(
            T.DLG_EDIT_PRODUCT if product else T.DLG_ADD_PRODUCT
        )
        self.setMinimumWidth(420)

        self.name_edit = QLineEdit()
        self.regular_edit = QLineEdit()
        self.regular_edit.setPlaceholderText(T.PH_REGULAR)
        self.website_edit = QLineEdit()
        self.website_edit.setPlaceholderText(T.PH_WEBSITE)
        self.gift_edit = QLineEdit()
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setFixedHeight(80)
        self.quantity_edit = QLineEdit()
        self.quantity_edit.setPlaceholderText(T.PH_QTY_OPTIONAL)

        self.blocks = {
            "name": FieldBlock(self.name_edit),
            "regular_price": FieldBlock(self.regular_edit),
            "website_price": FieldBlock(self.website_edit),
        }
        self.quantity_block = FieldBlock(self.quantity_edit)
        self._general = QLabel()
        self._general.setStyleSheet(ERROR_STYLE)
        self._general.setWordWrap(True)
        self._general.hide()

        form = QFormLayout()
        form.addRow(T.LBL_PRODUCT_NAME, self.blocks["name"])
        form.addRow(T.LBL_REGULAR_FIRST, self.blocks["regular_price"])
        form.addRow(T.LBL_WEBSITE_DISCOUNTED, self.blocks["website_price"])
        form.addRow(T.LBL_DEFAULT_GIFT, self.gift_edit)
        form.addRow(T.LBL_NOTES, self.notes_edit)
        form.addRow(T.LBL_COUNTED_QTY, self.quantity_block)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        localize_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._general)
        layout.addWidget(buttons)

        if product is not None:
            self.name_edit.setText(product.name)
            self.regular_edit.setText(
                format_money_input(product.regular_price)
            )
            self.website_edit.setText(
                format_money_input(product.website_price)
            )
            self.gift_edit.setText(product.default_gift_name or "")
            self.notes_edit.setPlainText(product.notes or "")
            if product.quantity is not None:
                self.quantity_edit.setText(str(product.quantity))

        self.regular_edit.textChanged.connect(lambda _t: self._update_hints())
        self.website_edit.textChanged.connect(lambda _t: self._update_hints())
        self._update_hints()

    def _update_hints(self) -> None:
        for key, edit in (
            ("regular_price", self.regular_edit),
            ("website_price", self.website_edit),
        ):
            self.blocks[key].set_hint(read_money(edit.text()).hint)

    def _clear_errors(self) -> None:
        for block in self.blocks.values():
            block.set_error(None)
        self.quantity_block.set_error(None)
        self.quantity_edit.setToolTip("")
        self.quantity_edit.setStyleSheet("")
        self._general.hide()

    def accept(self) -> None:
        self._clear_errors()
        regular = read_money(self.regular_edit.text())
        website = read_money(self.website_edit.text())
        problems = False
        for key, read in (
            ("regular_price", regular),
            ("website_price", website),
        ):
            if read.error is not None:
                self.blocks[key].set_error(read.error)
                problems = True
        if not " ".join(self.name_edit.text().split()):
            self.blocks["name"].set_error(T.VAL_NAME_REQUIRED)
            problems = True
        if problems or regular.value is None or website.value is None:
            return

        quantity: int | None = None
        if self.quantity_edit.text().strip():
            match parse_quantity(self.quantity_edit.text()):
                case Err(message):
                    self.quantity_block.set_error(message)
                    return
                case Ok(value):
                    quantity = value

        draft = ProductDraft(
            self.name_edit.text(),
            regular.value,
            website.value,
            self.gift_edit.text(),
            self.notes_edit.toPlainText(),
        )
        outcome = (
            self._repo.update(self._product.id, draft)
            if self._product is not None
            else self._repo.add(draft)
        )
        match outcome:
            case Err(error):
                self._show_repo_error(error)
            case Ok(saved):
                if quantity is not None and saved.quantity != quantity:
                    stock = self._repo.set_quantity(
                        saved.id, quantity, StockSource.MANUAL
                    )
                    if isinstance(stock, Err):
                        self._show_repo_error(stock.error)
                        return
                    saved = stock.value
                elif (
                    self._product is not None
                    and self._product.quantity is not None
                    and quantity is None
                ):
                    cleared = self._repo.clear_quantity(saved.id)
                    if isinstance(cleared, Err):
                        self._show_repo_error(cleared.error)
                        return
                    saved = cleared.value
                self.saved = saved
                super().accept()

    def _show_repo_error(self, error: RepoError) -> None:
        shown = False
        for detail in error.details:
            block = self.blocks.get(detail.field)
            if block is not None:
                block.set_error(detail.message)
                shown = True
        if error.code == "duplicate_name":
            self.blocks["name"].set_error(error.message)
            shown = True
        if not shown:
            self._general.setText(error.message)
            self._general.show()


class ProductsTab(QWidget):
    products_changed = Signal()
    import_finished = (
        Signal()
    )  # the import dialog closed (a backup may have run)

    def __init__(
        self,
        repo: ProductRepository,
        conn: sqlite3.Connection | None = None,
        backups: BackupManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repo = repo
        self._conn = conn
        self._backups = backups

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(T.PH_SEARCH)
        self.search_edit.setClearButtonEnabled(True)
        self.show_archived = QCheckBox(T.CHK_SHOW_ARCHIVED)

        self.table_model = ProductTableModel(self)
        self.table = QTableView()
        self.table.setObjectName("productsTable")
        self.table.setModel(self.table_model)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(110)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        self.add_button = QPushButton(T.BTN_ADD_PRODUCT)
        self.edit_button = QPushButton(T.BTN_EDIT)
        self.archive_button = QPushButton(T.BTN_ARCHIVE)
        self.import_button = QPushButton(T.BTN_IMPORT_CSV)
        self.import_button.setEnabled(conn is not None)
        self.bulk_archive_button = QPushButton(T.BTN_ARCHIVE_SELECTED)
        self.export_button = QPushButton(T.BTN_EXPORT_CSV)
        self.delete_button = QPushButton(T.BTN_DELETE_PRODUCT)

        top = QHBoxLayout()
        top.addWidget(self.search_edit, 1)
        top.addWidget(self.show_archived)
        bottom = QHBoxLayout()
        bottom.addWidget(self.add_button)
        bottom.addWidget(self.edit_button)
        bottom.addWidget(self.archive_button)
        bottom.addWidget(self.bulk_archive_button)
        bottom.addWidget(self.export_button)
        bottom.addWidget(self.delete_button)
        bottom.addStretch(1)
        bottom.addWidget(self.import_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)

        self.search_edit.textChanged.connect(lambda _t: self.reload())
        self.show_archived.toggled.connect(lambda _c: self.reload())
        self.add_button.clicked.connect(self._add)
        self.edit_button.clicked.connect(self._edit)
        self.archive_button.clicked.connect(self._toggle_archive)
        self.import_button.clicked.connect(lambda _c=False: self._import_csv())
        self.bulk_archive_button.clicked.connect(
            lambda _c=False: self._bulk_archive()
        )
        self.export_button.clicked.connect(lambda _c=False: self._export_csv())
        self.delete_button.clicked.connect(
            lambda _c=False: self._delete_product()
        )
        self.table.doubleClicked.connect(lambda _i: self._edit())
        self.table.selectionModel().selectionChanged.connect(
            lambda _s, _d: self._update_buttons()
        )
        self.reload()

    def reload(self) -> None:
        selected = self.selected_product()
        self.table_model.set_products(
            self._repo.search(
                self.search_edit.text(), self.show_archived.isChecked()
            )
        )
        self.table.resizeColumnsToContents()
        if selected is not None:
            self._select_id(selected.id)
        self._update_buttons()

    def selected_product(self) -> Product | None:
        rows = self.table.selectionModel().selectedRows()
        return self.table_model.product_at(rows[0].row()) if rows else None

    def selected_products(self) -> list[Product]:
        return [
            product
            for index in self.table.selectionModel().selectedRows()
            if (product := self.table_model.product_at(index.row()))
            is not None
        ]

    def _select_id(self, product_id: int) -> None:
        row = self.table_model.row_of(product_id)
        if row is not None:
            self.table.selectRow(row)

    def _update_buttons(self) -> None:
        products = self.selected_products()
        product = products[0] if len(products) == 1 else None
        self.edit_button.setEnabled(product is not None)
        self.archive_button.setEnabled(product is not None)
        self.delete_button.setEnabled(product is not None)
        self.archive_button.setText(
            T.BTN_RESTORE
            if product is not None and product.archived
            else T.BTN_ARCHIVE
        )
        self.add_button.setEnabled(product is None or not product.archived)
        self.bulk_archive_button.setEnabled(bool(products))
        self.bulk_archive_button.setText(
            T.BTN_RESTORE_SELECTED
            if products and all(p.archived for p in products)
            else T.BTN_ARCHIVE_SELECTED
        )

    def _import_csv(self) -> None:
        if self._conn is None:
            return
        dialog = ImportDialog(
            self._repo, self._conn, self._backups, parent=self
        )
        dialog.exec()
        self.reload()
        if dialog.summary is not None:
            self.products_changed.emit()
        self.import_finished.emit()

    def _add(self) -> None:
        dialog = ProductDialog(self._repo, parent=self)
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.saved is not None
        ):
            self.reload()
            self._select_id(dialog.saved.id)
            self.products_changed.emit()

    def _edit(self) -> None:
        product = self.selected_product()
        if product is None:
            return
        dialog = ProductDialog(self._repo, product, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()
            self.products_changed.emit()

    def _toggle_archive(self) -> None:
        product = self.selected_product()
        if product is None:
            return
        outcome = (
            self._repo.restore(product.id)
            if product.archived
            else self._repo.archive(product.id)
        )
        match outcome:
            case Err(error):
                show_warning(self, T.CANNOT_CHANGE_TITLE, error.message)
            case Ok(_):
                self.reload()
                self.products_changed.emit()

    def _bulk_archive(self) -> None:
        products = self.selected_products()
        if not products:
            return
        restoring = all(product.archived for product in products)
        action = (
            T.BTN_RESTORE_SELECTED if restoring else T.BTN_ARCHIVE_SELECTED
        )
        if not ask_yes_no(
            self,
            T.DLG_BULK_PRODUCTS,
            T.confirm_bulk_products(action, len(products)),
        ):
            return
        errors: list[str] = []
        for product in products:
            outcome = (
                self._repo.restore(product.id)
                if restoring
                else self._repo.archive(product.id)
            )
            if isinstance(outcome, Err):
                errors.append(outcome.error.message)
        self.reload()
        self.products_changed.emit()
        if errors:
            show_warning(self, T.CANNOT_CHANGE_TITLE, "\n".join(errors))

    def _export_csv(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self, T.EXPORT_DIALOG_TITLE, "products.csv", T.FILE_DIALOG_FILTER
        )
        if not path:
            return
        try:
            count = export_products_csv(
                self._repo.search(
                    self.search_edit.text(), self.show_archived.isChecked()
                ),
                Path(path),
            )
        except OSError as exc:
            show_warning(
                self, T.EXPORT_FAILED_TITLE, T.export_failed(str(exc))
            )
            return
        show_warning(self, T.EXPORT_DONE_TITLE, T.export_done(count))

    def _delete_product(self) -> None:
        product = self.selected_product()
        if product is None:
            return
        if not ask_yes_no(
            self, T.DLG_DELETE_PRODUCT, T.confirm_delete_product(product.name)
        ):
            return
        outcome = self._repo.delete_if_unused(product.id)
        match outcome:
            case Err(error):
                show_warning(self, T.CANNOT_CHANGE_TITLE, error.message)
            case Ok(_):
                self.reload()
                self.products_changed.emit()
