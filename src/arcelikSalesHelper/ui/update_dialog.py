from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.domain.result import Err, Ok
from arcelikSalesHelper.infrastructure.backups import (
    BackupManager,
    BackupReason,
)
from arcelikSalesHelper.infrastructure.csv_import import (
    Decision,
    ImportPlan,
    ImportSummary,
    apply_plan,
    index_products,
    plan_import,
)
from arcelikSalesHelper.infrastructure.repositories import (
    ProductRepository,
    utc_now,
)
from arcelikSalesHelper.infrastructure.scrape_import import (
    build_scrape_parsed,
    count_choices,
    plan_info,
    without_rows,
)
from arcelikSalesHelper.infrastructure.scrape_policy import (
    GateReason,
    is_suspicious_drop,
)
from arcelikSalesHelper.infrastructure.scrape_report import (
    ReportRow,
    build_report_rows,
    write_report_csv,
)
from arcelikSalesHelper.infrastructure.scrape_state import (
    current_gate,
    load_state,
    record_applied,
    record_crawl_success,
    try_begin_attempt,
)
from arcelikSalesHelper.infrastructure.scrapper.models import ScrapeOutcome

from .common import (
    ERROR_STYLE,
    HINT_STYLE,
    WARNING_STYLE,
    ask_yes_no,
    format_local_timestamp,
    show_critical,
    show_warning,
)
from .plan_preview import PlanPreviewWidget, price_text, scrape_cells
from .scrape_worker import ScrapeWorker

log = logging.getLogger(__name__)

PAGE_INTRO, PAGE_PROGRESS, PAGE_PREVIEW, PAGE_RESULT = range(4)
_ISO = "%Y-%m-%dT%H:%M:%SZ"
_APPLIED = {
    T.UPDATE_STATUS_CREATED,
    T.UPDATE_STATUS_UPDATED,
    T.UPDATE_STATUS_RESTORED,
}

WorkerFactory = Callable[[], Any]


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(_ISO)


def _note(text: str, style: str = HINT_STYLE) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(style)
    return label


class UpdateDialog(QDialog):
    """Intro -> progress -> preview -> result. Nothing is written before the
    employee confirms; a verified ``pre_scrape`` backup precedes every apply.
    """

    def __init__(
        self,
        repo: ProductRepository,
        conn: sqlite3.Connection,
        backups: BackupManager,
        parent: QWidget | None = None,
        *,
        worker_factory: WorkerFactory = ScrapeWorker,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(parent)
        self._repo = repo
        self._conn = conn
        self._backups = backups
        self._worker_factory = worker_factory
        self._clock = clock
        self._worker: Any = None
        self._plan: ImportPlan | None = None
        self._partial = False
        self._drop = False
        self._report_rows: tuple[ReportRow, ...] = ()
        self._shown_rows: tuple[ReportRow, ...] = ()
        self.applied_summary: ImportSummary | None = None

        self.setWindowTitle(T.UPDATE_TITLE)
        self.resize(1100, 700)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_intro())
        self.stack.addWidget(self._build_progress())
        self.stack.addWidget(self._build_preview())
        self.stack.addWidget(self._build_result())
        layout = QVBoxLayout(self)
        layout.addWidget(self.stack)
        self.refresh_intro()

    # ---- page construction ----------------------------------------------

    def _build_intro(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        for text in (
            T.UPDATE_INTRO,
            T.UPDATE_SCOPE_NOTE,
            T.UPDATE_BACKUP_NOTE,
            T.UPDATE_DURATION_NOTE,
        ):
            layout.addWidget(_note(text))
        self.last_run_label = QLabel()
        self.gate_label = QLabel()
        self.gate_label.setWordWrap(True)
        self.quota_label = QLabel()
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.hide()
        self.start_button = QPushButton(T.UPDATE_START)
        self.intro_close_button = QPushButton(T.BTN_CLOSE)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.intro_close_button)
        for widget in (self.last_run_label, self.gate_label, self.quota_label):
            layout.addWidget(widget)
        layout.addWidget(self.message_label)
        layout.addStretch(1)
        layout.addLayout(buttons)
        self.start_button.clicked.connect(lambda _c=False: self._start())
        self.intro_close_button.clicked.connect(self.reject)
        return page

    def _build_progress(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.progress_label = QLabel(T.UPDATE_PROGRESS_START)
        self.progress_label.setWordWrap(True)
        self.progress_detail = QLabel()
        self.progress_detail.setStyleSheet(HINT_STYLE)
        bar = QProgressBar()
        bar.setRange(0, 0)  # indeterminate
        self.cancel_button = QPushButton(T.UPDATE_CANCEL)
        layout.addStretch(1)
        layout.addWidget(self.progress_label)
        layout.addWidget(bar)
        layout.addWidget(self.progress_detail)
        layout.addWidget(self.cancel_button)
        layout.addStretch(1)
        self.cancel_button.clicked.connect(
            lambda _c=False: self._cancel_scan()
        )
        return page

    def _build_preview(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.banner = _note("", WARNING_STYLE)
        self.banner.hide()
        self.preview = PlanPreviewWidget(
            T.UPDATE_PREVIEW_COLUMNS,
            scrape_cells,
            6,
            default_conflict=Decision.SKIP,
            choose_new=True,
            fix_message=T.UPDATE_FIX_ROWS,
            nothing_message=T.UPDATE_NOTHING,
        )
        self.partial_check = QCheckBox(T.UPDATE_PARTIAL_CHECK)
        self.partial_check.hide()
        self.status_label = _note("")
        self.apply_button = QPushButton(T.UPDATE_APPLY)
        self.apply_button.setEnabled(False)
        self.preview_close_button = QPushButton(T.BTN_CLOSE)
        buttons = QHBoxLayout()
        buttons.addWidget(self.status_label, 1)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.preview_close_button)
        layout.addWidget(self.banner)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.partial_check)
        layout.addLayout(buttons)
        self.preview.changed.connect(self._update_apply)
        self.partial_check.toggled.connect(lambda _c: self._update_apply())
        self.apply_button.clicked.connect(lambda _c=False: self._apply())
        self.preview_close_button.clicked.connect(self.reject)
        return page

    def _build_result(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.result_summary = QLabel()
        self.result_summary.setWordWrap(True)
        self.show_unchanged_check = QCheckBox(T.UPDATE_SHOW_UNCHANGED)
        self.result_table = QTableWidget(0, len(T.UPDATE_RESULT_COLUMNS))
        self.result_table.setHorizontalHeaderLabels(
            list(T.UPDATE_RESULT_COLUMNS)
        )
        self.result_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.result_table.verticalHeader().hide()
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.export_button = QPushButton(T.UPDATE_EXPORT_REPORT)
        self.result_close_button = QPushButton(T.BTN_CLOSE)
        buttons = QHBoxLayout()
        buttons.addWidget(self.export_button)
        buttons.addStretch(1)
        buttons.addWidget(self.result_close_button)
        layout.addWidget(self.result_summary)
        layout.addWidget(self.show_unchanged_check)
        layout.addWidget(self.result_table, 1)
        layout.addLayout(buttons)
        self.show_unchanged_check.toggled.connect(
            lambda _c: self._fill_result()
        )
        self.export_button.clicked.connect(lambda _c=False: self._export())
        self.result_close_button.clicked.connect(self.accept)
        return page

    # ---- intro -----------------------------------------------------------

    def refresh_intro(self) -> None:
        now = self._clock()
        state = load_state(self._conn)
        gate = current_gate(self._conn, now)
        self.last_run_label.setText(
            T.update_last_run(format_local_timestamp(_iso(state.last_success)))
            if state.last_success is not None
            else T.UPDATE_NEVER_RUN
        )
        if gate.reason is not GateReason.OK and gate.retry_at is not None:
            remaining = (
                0
                if gate.remaining is None
                else int(gate.remaining.total_seconds())
            )
            self.gate_label.setText(
                T.update_cooldown(
                    format_local_timestamp(_iso(gate.retry_at)),
                    T.duration_text(remaining),
                )
            )
            self.gate_label.setStyleSheet(WARNING_STYLE)
        else:
            self.gate_label.setText("")
        self.quota_label.setText(T.update_quota(gate.used, gate.limit))
        self.start_button.setEnabled(gate.allowed)

    def _back_to_intro(self, message: str | None, *, error: bool) -> None:
        if message:
            self.message_label.setStyleSheet(
                ERROR_STYLE if error else HINT_STYLE
            )
            self.message_label.setText(message)
            self.message_label.show()
        else:
            self.message_label.hide()
        self.refresh_intro()
        self.stack.setCurrentIndex(PAGE_INTRO)

    # ---- crawl -----------------------------------------------------------

    def _start(self) -> None:
        gate = try_begin_attempt(self._conn, self._clock())
        if not gate.allowed:  # re-checked at the click, not only at open
            self.refresh_intro()
            return
        self.message_label.hide()
        worker = self._worker_factory()
        worker.progress.connect(self._on_progress)
        worker.finished_outcome.connect(self._on_outcome)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        self.progress_label.setText(T.UPDATE_PROGRESS_START)
        self.progress_detail.setText("")
        self.cancel_button.setEnabled(True)
        self.stack.setCurrentIndex(PAGE_PROGRESS)
        worker.start()

    def _cancel_scan(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        self.cancel_button.setEnabled(False)
        self.progress_label.setText(T.UPDATE_CANCELLING)

    def _on_progress(self, progress: Any) -> None:
        if self._worker is None or not progress.category:
            return
        self.progress_label.setText(
            T.update_progress(
                progress.category,
                progress.categories_done,
                progress.categories_total,
            )
        )
        self.progress_detail.setText(
            T.update_progress_detail(progress.products_found)
        )

    def _release_worker(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()

    def _stop_worker(self) -> None:
        worker = self._worker
        if worker is None:
            return
        worker.cancel()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            worker.wait()
        finally:
            QApplication.restoreOverrideCursor()
        self._release_worker()

    def _on_failed(self, message: str) -> None:
        if self._worker is None:
            return
        self._release_worker()
        self._back_to_intro(message, error=True)

    def _on_outcome(self, outcome: ScrapeOutcome) -> None:
        if self._worker is None:  # dialog was closed meanwhile
            return
        self._release_worker()
        if outcome.cancelled:
            self._back_to_intro(T.UPDATE_CANCELLED, error=False)
            return
        if outcome.error is not None:
            self._back_to_intro(outcome.error.message, error=True)
            return
        self._prepare_preview(outcome)

    # ---- preview ---------------------------------------------------------

    def _prepare_preview(self, outcome: ScrapeOutcome) -> None:
        state = load_state(self._conn)
        count = len(outcome.products)
        self._drop = is_suspicious_drop(count, state.product_count)
        self._partial = not outcome.complete
        try:
            record_crawl_success(
                self._conn,
                self._clock(),
                count,
                complete=outcome.complete and not self._drop,
            )
        except sqlite3.Error:
            log.exception("could not record the crawl result")
        existing = index_products(self._repo.search("", include_archived=True))
        build = build_scrape_parsed(
            outcome.products, existing, partial=self._partial
        )
        plan = plan_import(build.parsed, existing)
        info = plan_info(build, plan)
        self._plan = plan
        self.preview.set_plan(
            plan,
            T.update_counts(
                info.scraped,
                info.new,
                info.conflicts,
                info.unchanged,
                info.without_price,
                info.errors,
            ),
        )
        banner: list[str] = []
        if self._drop:
            banner.append(T.UPDATE_SITE_CHANGED)
        if self._partial:
            banner.append(
                T.update_partial(
                    outcome.categories_done, outcome.categories_total
                )
            )
        self.banner.setText("\n".join(banner))
        self.banner.setVisible(bool(banner))
        blocker_state = self.partial_check.blockSignals(True)
        self.partial_check.setChecked(False)
        self.partial_check.blockSignals(blocker_state)
        self.partial_check.setVisible(self._partial)
        self.stack.setCurrentIndex(PAGE_PREVIEW)
        self._update_apply()

    def _update_apply(self) -> None:
        if self._plan is None:
            self.apply_button.setEnabled(False)
            return
        reason = self.preview.blocking_reason()
        if reason is None and self._drop:
            reason = T.UPDATE_SITE_CHANGED  # no override
        if (
            reason is None
            and self._partial
            and not self.partial_check.isChecked()
        ):
            reason = T.UPDATE_NEED_PARTIAL
        self.status_label.setText(reason or T.UPDATE_READY)
        self.apply_button.setEnabled(reason is None)

    # ---- apply -----------------------------------------------------------

    def _apply(self) -> None:
        plan = self._plan
        if plan is None:
            return
        decisions = self.preview.decisions()
        skipped_new = self.preview.new_skipped()
        effective = without_rows(plan, skipped_new)
        counts = count_choices(effective, decisions)
        if counts.total == 0:  # nothing to do: no backup, no write
            self.status_label.setText(T.UPDATE_NOTHING)
            return
        if not ask_yes_no(
            self,
            T.UPDATE_CONFIRM_TITLE,
            T.update_confirm(counts.updated, counts.created, counts.restored),
        ):
            return
        backup = self._backups.run(BackupReason.PRE_SCRAPE)
        if isinstance(backup, Err):  # no override for a bulk price write
            show_critical(
                self,
                T.UPDATE_BACKUP_FAILED_TITLE,
                T.update_backup_failed(backup.error.message),
            )
            return
        result = apply_plan(
            self._conn,
            effective,
            decisions,
            import_valid_only=bool(effective.errors),
        )
        match result:
            case Err(failure):
                show_critical(self, T.IMPORT_FAILED_TITLE, failure.message)
            case Ok(summary):
                self.applied_summary = summary
                self._report_rows = build_report_rows(
                    plan, decisions, skipped_new
                )
                try:
                    record_applied(self._conn, counts.total)
                except sqlite3.Error:
                    log.exception("could not record the change count")
                self.result_summary.setText("\n".join(summary.lines()))
                self._fill_result()
                self.stack.setCurrentIndex(PAGE_RESULT)

    # ---- result ----------------------------------------------------------

    def _fill_result(self) -> None:
        rows = (
            self._report_rows
            if self.show_unchanged_check.isChecked()
            else tuple(r for r in self._report_rows if r.status in _APPLIED)
        )
        self._shown_rows = rows
        self.result_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            cells = (
                row.name,
                row.status,
                price_text(row.old_regular, website=False),
                price_text(row.new_regular, website=False),
                price_text(row.old_website, website=True),
                price_text(row.new_website, website=True),
            )
            for c, text in enumerate(cells):
                self.result_table.setItem(r, c, QTableWidgetItem(text))
        self.result_table.resizeColumnsToContents()

    def _export(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self,
            T.UPDATE_EXPORT_TITLE,
            "degisiklik-raporu.csv",
            T.FILE_DIALOG_FILTER,
        )
        if not path:
            return
        try:
            write_report_csv(self._shown_rows, Path(path))
        except OSError as exc:
            show_warning(
                self,
                T.UPDATE_EXPORT_FAILED_TITLE,
                T.update_export_failed(str(exc)),
            )
            return
        show_warning(self, T.UPDATE_DONE_TITLE, T.update_export_done(path))

    # ---- closing ---------------------------------------------------------

    def reject(self) -> None:
        self._stop_worker()  # never leave a thread touching a dead dialog
        super().reject()
