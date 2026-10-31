from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from arcelikSalesHelper.infrastructure.scrape_state import (
    record_crawl_success,
    try_begin_attempt,
)
from arcelikSalesHelper.infrastructure.scrapper.models import (
    ScrapedProduct,
    ScrapeError,
    ScrapeErrorCode,
    ScrapeOutcome,
)
from PySide6.QtCore import QObject, Signal

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.domain.products import ProductDraft
from arcelikSalesHelper.domain.result import Err, Ok
from arcelikSalesHelper.infrastructure.backups import (
    BackupError,
    BackupInfo,
    BackupReason,
)
from arcelikSalesHelper.infrastructure.database import open_database
from arcelikSalesHelper.infrastructure.repositories import ProductRepository
from arcelikSalesHelper.ui import update_dialog as ud
from arcelikSalesHelper.ui.update_dialog import (
    PAGE_INTRO,
    PAGE_PREVIEW,
    PAGE_RESULT,
    UpdateDialog,
)

D = Decimal
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


class FakeWorker(QObject):
    progress = Signal(object)
    finished_outcome = Signal(object)
    failed = Signal(str)
    last: "FakeWorker"

    def __init__(self):
        super().__init__()
        FakeWorker.last = self
        self.cancelled = False

    def start(self): ...
    def cancel(self):
        self.cancelled = True

    def wait(self, *_a):
        return True


class FakeBackups:
    def __init__(self, fail=False, on_run=None):
        self.calls, self.fail, self.on_run = [], fail, on_run

    def run(self, reason):
        self.calls.append(reason)
        if self.on_run:
            self.on_run()
        if self.fail:
            return Err(BackupError("failed", "boom"))
        return Ok(BackupInfo(Path("b.sqlite"), NOW, reason, 0))


def outcome(products, **kw):
    return ScrapeOutcome(tuple(products), 1, 1, 0, 0, 0, 1.0, **kw)


@pytest.fixture
def conn(tmp_path):
    opened = open_database(tmp_path / "t.sqlite")
    assert isinstance(opened, Ok)
    yield opened.value
    opened.value.close()


@pytest.fixture(autouse=True)
def _dialogs(monkeypatch):
    monkeypatch.setattr(ud, "ask_yes_no", lambda *a, **k: True)
    monkeypatch.setattr(ud, "show_critical", lambda *a, **k: None)
    monkeypatch.setattr(ud, "show_warning", lambda *a, **k: None)


def make(conn, backups, now=NOW):
    return UpdateDialog(
        ProductRepository(conn),
        conn,
        backups,
        worker_factory=FakeWorker,
        clock=lambda: now,
    )


def run_scan(dialog, products, **kw):
    dialog.start_button.click()
    FakeWorker.last.finished_outcome.emit(outcome(products, **kw))


def seed(conn):
    repo = ProductRepository(conn)
    added = repo.add(ProductDraft("ADE 500", D(100), D(90)))
    assert isinstance(added, Ok)
    return repo, added.value.id


def test_cooldown_disables_start(qapp, conn):
    try_begin_attempt(conn, NOW - timedelta(hours=1))
    dialog = make(conn, FakeBackups())
    assert not dialog.start_button.isEnabled()
    assert "1/5" in dialog.quota_label.text()


def test_defaults_skip_conflicts_add_new_and_backup_first(qapp, conn):
    repo, pid = seed(conn)

    def backup_sees_old_prices():
        assert repo.get(pid).regular_price == D(100)  # nothing written yet

    backups = FakeBackups(on_run=backup_sees_old_prices)
    dialog = make(conn, backups)
    run_scan(
        dialog,
        [
            ScrapedProduct("ADE 500", D(120), D(110)),
            ScrapedProduct("NEW 1", D(5), D(4)),
        ],
    )
    assert dialog.stack.currentIndex() == PAGE_PREVIEW
    assert dialog.apply_button.isEnabled()
    dialog.apply_button.click()
    assert backups.calls == [BackupReason.PRE_SCRAPE]
    assert repo.get(pid).regular_price == D(100)  # skipped by default
    assert len(repo.search("NEW 1")) == 1  # added by default
    assert dialog.stack.currentIndex() == PAGE_RESULT
    assert dialog.applied_summary.created == 1
    assert dialog.result_table.rowCount() == 1  # only what changed


def test_update_all_then_apply(qapp, conn):
    repo, pid = seed(conn)
    dialog = make(conn, FakeBackups())
    run_scan(dialog, [ScrapedProduct("ADE 500", D(120), D(110))])
    assert not dialog.apply_button.isEnabled()  # all skipped: no effect
    dialog.preview.update_all_button.click()
    assert dialog.apply_button.isEnabled()
    dialog.apply_button.click()
    assert repo.get(pid).regular_price == D(120)
    assert repo.get(pid).website_price == D(110)


def test_skipping_new_rows(qapp, conn):
    repo, _ = seed(conn)
    backups = FakeBackups()
    dialog = make(conn, backups)
    run_scan(dialog, [ScrapedProduct("NEW 1", D(5), D(4))])
    dialog.preview.skip_new_button.click()
    assert not dialog.apply_button.isEnabled()
    assert backups.calls == []
    assert repo.search("NEW 1") == []


def test_backup_failure_blocks_apply(qapp, conn):
    repo, pid = seed(conn)
    dialog = make(conn, FakeBackups(fail=True))
    run_scan(dialog, [ScrapedProduct("NEW 1", D(5), D(4))])
    dialog.apply_button.click()
    assert repo.search("NEW 1") == []
    assert dialog.stack.currentIndex() == PAGE_PREVIEW
    assert dialog.applied_summary is None


def test_no_changes_means_no_backup(qapp, conn):
    seed(conn)
    backups = FakeBackups()
    dialog = make(conn, backups)
    run_scan(dialog, [ScrapedProduct("ADE 500", D(100), D(90))])
    assert not dialog.apply_button.isEnabled()
    assert dialog.status_label.text() == T.UPDATE_NOTHING
    assert backups.calls == []


def test_suspicious_drop_blocks_apply(qapp, conn):
    record_crawl_success(conn, NOW - timedelta(days=2), 100, complete=True)
    dialog = make(conn, FakeBackups())
    run_scan(dialog, [ScrapedProduct(f"P {i}", D(1), D(1)) for i in range(10)])
    assert not dialog.apply_button.isEnabled()
    assert dialog.status_label.text() == T.UPDATE_SITE_CHANGED


def test_partial_crawl_needs_checkbox(qapp, conn):
    dialog = make(conn, FakeBackups())
    run_scan(
        dialog, [ScrapedProduct("NEW 1", D(1), D(1))], categories_failed=1
    )
    assert not dialog.partial_check.isHidden()
    assert not dialog.apply_button.isEnabled()
    dialog.partial_check.setChecked(True)
    assert dialog.apply_button.isEnabled()


def test_cancel_discards_everything(qapp, conn):
    repo, _ = seed(conn)
    dialog = make(conn, FakeBackups())
    run_scan(dialog, [ScrapedProduct("NEW 1", D(1), D(1))], cancelled=True)
    assert dialog.stack.currentIndex() == PAGE_INTRO
    assert repo.search("NEW 1") == []
    assert dialog.applied_summary is None


def test_crawl_error_returns_to_intro_and_still_counts(qapp, conn):
    dialog = make(conn, FakeBackups())
    error = ScrapeError(ScrapeErrorCode.BLOCKED, T.UPDATE_BLOCKED)
    run_scan(dialog, [], error=error)
    assert dialog.stack.currentIndex() == PAGE_INTRO
    assert dialog.message_label.text() == T.UPDATE_BLOCKED
    assert (
        not dialog.start_button.isEnabled()
    )  # the attempt started the cooldown
