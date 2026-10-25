from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

from arcelikSalesHelper.constants import DATA_DIR_ENV_VAR
from arcelikSalesHelper.domain.products import ProductDraft
from arcelikSalesHelper.domain.result import Err
from arcelikSalesHelper.infrastructure import backups
from arcelikSalesHelper.infrastructure.backups import (
    BackupManager,
    BackupReason,
    list_backups,
)
from arcelikSalesHelper.infrastructure.repositories import ProductRepository
from arcelikSalesHelper.paths import resolve_paths
from arcelikSalesHelper.ui.main_window import MainWindow


def make_window(db, tmp_path: Path, clock):  # type: ignore[no-untyped-def]
    paths = resolve_paths({DATA_DIR_ENV_VAR: str(tmp_path / "data")})
    manager = BackupManager(db, paths.backup_dir, clock)
    return MainWindow(db, paths, manager), manager, paths


def fail_verification(monkeypatch):  # type: ignore[no-untyped-def]
    ctx = monkeypatch.context()
    m = ctx.__enter__()
    m.setattr(backups, "verify_backup_file", lambda p, v: Err("corrupt"))
    return ctx


def test_settings_shows_paths_and_no_backup_yet(
    qtbot, db, tmp_path, clock
) -> None:  # type: ignore[no-untyped-def]
    window, _, paths = make_window(db, tmp_path, clock)
    qtbot.addWidget(window)
    tab = window.settings_tab
    assert (
        tab.db_edit.text() == str(paths.db_path) and tab.db_edit.isReadOnly()
    )
    assert tab.backup_dir_edit.text() == str(paths.backup_dir)
    assert tab.latest_label.text() == "No backup yet."
    assert window.backup_banner.isHidden() and tab.failure_label.isHidden()


def test_back_up_now_creates_a_verified_backup_and_reports_it(
    qtbot, db, tmp_path, clock
) -> None:  # type: ignore[no-untyped-def]
    window, _, paths = make_window(db, tmp_path, clock)
    qtbot.addWidget(window)
    tab = window.settings_tab
    with qtbot.waitSignal(tab.backup_finished):
        tab.backup_button.click()
    assert "verified" in tab.feedback.text()
    assert len(list_backups(paths.backup_dir)) == 1
    assert (
        ".sqlite" in tab.latest_label.text()
        and "manual" in tab.latest_label.text()
    )
    assert window.backup_banner.isHidden()


def test_failed_backup_shows_a_banner_until_a_backup_succeeds(
    qtbot, db, tmp_path, clock, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    window, _, _ = make_window(db, tmp_path, clock)
    qtbot.addWidget(window)
    tab = window.settings_tab

    ctx = fail_verification(monkeypatch)
    tab.backup_button.click()
    ctx.__exit__(None, None, None)
    assert "failed" in tab.feedback.text()
    assert not tab.failure_label.isHidden()
    assert not window.backup_banner.isHidden()
    assert (
        "failed" in window.backup_banner.text()
        and "Back up now" in window.backup_banner.text()
    )

    tab.backup_button.click()
    assert window.backup_banner.isHidden() and tab.failure_label.isHidden()


def test_a_failure_from_startup_is_visible_when_the_window_opens(
    qtbot, db, tmp_path, clock, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    paths = resolve_paths({DATA_DIR_ENV_VAR: str(tmp_path / "data")})
    manager = BackupManager(db, paths.backup_dir, clock)
    ctx = fail_verification(monkeypatch)
    manager.run(BackupReason.STARTUP)
    ctx.__exit__(None, None, None)

    window = MainWindow(db, paths, manager)
    qtbot.addWidget(window)
    assert not window.backup_banner.isHidden()
    assert "startup" in window.backup_banner.text()


def test_closing_after_changes_creates_a_close_backup(
    qtbot, db, tmp_path, clock
) -> None:  # type: ignore[no-untyped-def]
    window, _, paths = make_window(db, tmp_path, clock)
    qtbot.addWidget(window)
    window.show()
    ProductRepository(db, lambda: datetime(2026, 1, 1, tzinfo=UTC)).add(
        ProductDraft("Fridge", D(5000), D(4000))
    )
    window.close()
    [backup] = list_backups(paths.backup_dir)
    assert backup.reason == "close"


def test_closing_without_changes_makes_no_backup(
    qtbot, db, tmp_path, clock
) -> None:  # type: ignore[no-untyped-def]
    window, _, paths = make_window(db, tmp_path, clock)
    qtbot.addWidget(window)
    window.show()
    window.close()
    assert list_backups(paths.backup_dir) == []


def test_window_without_a_backup_manager_still_works(
    qtbot, db, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    paths = resolve_paths({DATA_DIR_ENV_VAR: str(tmp_path / "data")})
    window = MainWindow(db, paths)
    qtbot.addWidget(window)
    assert not window.settings_tab.backup_button.isEnabled()
    window.shutdown_backup()  # no-op
