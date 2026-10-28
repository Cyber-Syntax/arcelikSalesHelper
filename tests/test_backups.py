import os
import shutil
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from arcelikSalesHelper.domain.products import ProductDraft
from arcelikSalesHelper.domain.result import Err, Ok
from arcelikSalesHelper.infrastructure import backups
from arcelikSalesHelper.infrastructure.backups import (
    BackupError,
    BackupManager,
    BackupReason,
    PreMigrationBackup,
    create_backup,
    list_backups,
    needs_close_backup,
    needs_startup_backup,
    verify_backup_file,
)
from arcelikSalesHelper.infrastructure.database import (
    load_migrations,
    open_database,
    schema_version,
)
from arcelikSalesHelper.infrastructure.repositories import ProductRepository

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
FRIDGE = ProductDraft("Fridge", D(5000), D(4000))


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    return tmp_path / "backups"


def make(db, backup_dir, reason=BackupReason.MANUAL, now=T0, **kw):  # type: ignore[no-untyped-def]
    result = create_backup(db, backup_dir, reason, now=now, **kw)
    assert isinstance(result, Ok), result
    return result.value


def names(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


# ---- creating -------------------------------------------------------------


def test_backup_is_a_verified_single_file_copy(db, repo, backup_dir) -> None:  # type: ignore[no-untyped-def]
    repo.add(FRIDGE)
    info = make(db, backup_dir)
    assert (
        info.path.name == "arcelikSalesHelper-20260101T120000Z-manual.sqlite"
    )
    assert names(backup_dir) == [
        info.path.name
    ]  # no temp, -wal or -shm leftovers

    copy = sqlite3.connect(info.path)
    assert copy.execute("SELECT name FROM products").fetchall() == [
        ("Fridge",)
    ]
    assert copy.execute("PRAGMA user_version").fetchone()[0] == schema_version(
        db
    )
    assert copy.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    copy.close()


def test_a_backup_can_be_opened_as_a_database(
    db, repo, backup_dir, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    repo.add(FRIDGE)
    info = make(db, backup_dir)
    restored = tmp_path / "restored.sqlite"
    shutil.copy(info.path, restored)
    result = open_database(restored)
    assert isinstance(result, Ok)
    assert [p.name for p in ProductRepository(result.value).search()] == [
        "Fridge"
    ]
    result.value.close()


def test_creating_a_backup_does_not_touch_the_live_database(
    db, repo, backup_dir
) -> None:  # type: ignore[no-untyped-def]
    repo.add(FRIDGE)
    before = db.total_changes
    make(db, backup_dir)
    assert db.total_changes == before
    assert db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1


def test_backup_is_refused_while_a_transaction_is_open(db, backup_dir) -> None:  # type: ignore[no-untyped-def]
    db.execute("BEGIN IMMEDIATE")
    result = create_backup(db, backup_dir, BackupReason.MANUAL, now=T0)
    db.execute("ROLLBACK")
    assert isinstance(result, Err) and result.error.code == "busy"


# ---- verification ---------------------------------------------------------


def test_verify_accepts_a_good_copy_and_rejects_bad_ones(
    db, backup_dir, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    info = make(db, backup_dir)
    version = schema_version(db)
    assert isinstance(verify_backup_file(info.path, version), Ok)
    assert isinstance(verify_backup_file(info.path, version + 1), Err)

    garbage = tmp_path / "garbage.sqlite"
    garbage.write_bytes(b"not a database" * 200)
    assert isinstance(verify_backup_file(garbage, version), Err)
    assert isinstance(
        verify_backup_file(tmp_path / "missing.sqlite", version), Err
    )


def test_failed_verification_publishes_nothing_and_keeps_old_backups(  # type: ignore[no-untyped-def]
    db, backup_dir, monkeypatch
) -> None:
    for i in range(3):
        make(db, backup_dir, now=T0 + timedelta(seconds=i))
    monkeypatch.setattr(
        backups, "verify_backup_file", lambda p, v: Err("corrupt")
    )
    result = create_backup(
        db,
        backup_dir,
        BackupReason.MANUAL,
        now=T0 + timedelta(seconds=10),
        keep=1,
    )
    assert (
        isinstance(result, Err) and result.error.code == "verification_failed"
    )
    assert "corrupt" in result.error.message
    assert (
        len(names(backup_dir)) == 3
    )  # nothing new, nothing rotated, no temp file left


def test_copy_failure_cleans_up_the_temp_file(
    db, backup_dir, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    def boom(conn: sqlite3.Connection, tmp: Path) -> None:
        tmp.write_bytes(b"partial")
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(backups, "_copy", boom)
    result = create_backup(db, backup_dir, BackupReason.MANUAL, now=T0)
    assert isinstance(result, Err) and result.error.code == "failed"
    assert "disk full" in result.error.message
    assert names(backup_dir) == []


# ---- naming and retention -------------------------------------------------


def test_same_second_backups_get_a_counter_and_the_counter_is_newer(
    db, backup_dir
) -> None:  # type: ignore[no-untyped-def]
    make(db, backup_dir)
    second = make(db, backup_dir)
    assert second.path.name.endswith("-manual-1.sqlite")
    third = make(db, backup_dir, keep=1)
    assert third.path.name.endswith("-manual-2.sqlite")
    assert names(backup_dir) == [third.path.name]


def test_retention_keeps_the_newest_30(db, backup_dir) -> None:  # type: ignore[no-untyped-def]
    for i in range(35):
        make(db, backup_dir, now=T0 + timedelta(seconds=i))
    remaining = names(backup_dir)
    assert len(remaining) == 30
    assert remaining[0] == "arcelikSalesHelper-20260101T120005Z-manual.sqlite"
    assert remaining[-1] == "arcelikSalesHelper-20260101T120034Z-manual.sqlite"


def test_rotation_ignores_unrelated_files_and_removes_only_stale_temp_files(  # type: ignore[no-untyped-def]
    db, backup_dir
) -> None:
    backup_dir.mkdir()
    (backup_dir / "notes.txt").write_text("keep me")
    (backup_dir / "arcelikSalesHelper.sqlite").write_bytes(
        b"live-looking file"
    )
    fresh = backup_dir / ".tmp-fresh.sqlite"
    fresh.write_bytes(b"x")
    stale = backup_dir / ".tmp-stale.sqlite"
    stale.write_bytes(b"x")
    old = time.time() - 7200
    os.utime(stale, (old, old))

    make(db, backup_dir, keep=1)
    make(db, backup_dir, now=T0 + timedelta(seconds=1), keep=1)

    remaining = names(backup_dir)
    assert {
        "notes.txt",
        "arcelikSalesHelper.sqlite",
        ".tmp-fresh.sqlite",
    } <= set(remaining)
    assert ".tmp-stale.sqlite" not in remaining
    assert (
        len(
            [
                n
                for n in remaining
                if n.endswith("-manual.sqlite") and "-2026" in n
            ]
        )
        == 1
    )


def test_a_rotation_error_does_not_fail_the_backup(
    db, backup_dir, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    make(db, backup_dir)

    def deny(path: Path) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(backups, "_unlink", deny)
    info = make(db, backup_dir, now=T0 + timedelta(seconds=1), keep=1)
    assert len(info.rotation_errors) == 1 and info.deleted == ()
    assert len(list_backups(backup_dir)) == 2


# ---- policy ---------------------------------------------------------------


def test_startup_policy_around_the_24h_boundary() -> None:
    assert needs_startup_backup(None, T0)
    assert not needs_startup_backup(T0 - timedelta(hours=23, minutes=59), T0)
    assert not needs_startup_backup(
        T0 - timedelta(hours=24), T0
    )  # exactly 24h is not "older"
    assert needs_startup_backup(T0 - timedelta(hours=24, seconds=1), T0)
    assert needs_startup_backup(
        T0 + timedelta(minutes=1), T0
    )  # clock moved back


def test_close_policy() -> None:
    assert needs_close_backup(True) and not needs_close_backup(False)


# ---- manager --------------------------------------------------------------


@pytest.fixture
def manager(db, backup_dir, clock):  # type: ignore[no-untyped-def]
    return BackupManager(db, backup_dir, clock)


def test_success_clears_an_earlier_failure(manager, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with monkeypatch.context() as m:
        m.setattr(backups, "verify_backup_file", lambda p, v: Err("corrupt"))
        assert isinstance(manager.run(BackupReason.STARTUP), Err)
    failure = manager.status().failure
    assert failure is not None and failure.reason == "startup"
    assert (
        "corrupt" in failure.message and failure.at == "2026-01-01T12:00:00Z"
    )

    assert isinstance(manager.run(BackupReason.MANUAL), Ok)
    status = manager.status()
    assert (
        status.failure is None
        and status.count == 1
        and status.latest is not None
    )
    keys = {r["key"] for r in db.execute("SELECT key FROM app_metadata")}
    assert (
        "last_backup_success_at" in keys
        and "last_backup_failure_at" not in keys
    )


def test_change_tracking_ignores_the_backup_bookkeeping(manager, repo) -> None:  # type: ignore[no-untyped-def]
    assert not manager.has_changes()
    repo.add(FRIDGE)
    assert manager.has_changes()
    assert isinstance(manager.run(BackupReason.MANUAL), Ok)
    assert not manager.has_changes()
    manager.mark_dirty()
    assert manager.has_changes()
    assert isinstance(manager.run(BackupReason.MANUAL), Ok)
    assert not manager.has_changes()


def test_a_failed_backup_leaves_the_changes_pending(
    manager, repo, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    repo.add(FRIDGE)
    with monkeypatch.context() as m:
        m.setattr(backups, "verify_backup_file", lambda p, v: Err("corrupt"))
        manager.run(BackupReason.CLOSE)
    assert manager.has_changes()


def test_startup_backup_runs_when_missing_or_old_only(
    manager, clock, backup_dir
) -> None:  # type: ignore[no-untyped-def]
    assert isinstance(
        manager.run_startup_backup_if_needed(), Ok
    )  # none exists
    assert manager.run_startup_backup_if_needed() is None
    clock.advance(24 * 3600)
    assert manager.run_startup_backup_if_needed() is None  # exactly 24h
    clock.advance(1)
    assert isinstance(manager.run_startup_backup_if_needed(), Ok)

    for path in list_backups(backup_dir):
        path.path.unlink()
    assert isinstance(
        manager.run_startup_backup_if_needed(), Ok
    )  # files gone: back up again


def test_close_backup_runs_only_after_changes_and_only_once(
    manager, repo
) -> None:  # type: ignore[no-untyped-def]
    assert manager.run_close_backup_if_needed() is None
    repo.add(FRIDGE)
    result = manager.run_close_backup_if_needed()
    assert isinstance(result, Ok) and "-close" in result.value.path.name
    assert manager.run_close_backup_if_needed() is None


# ---- pre-migration hook ---------------------------------------------------


def test_pre_migration_hook_backs_up_the_old_schema(
    tmp_path, backup_dir
) -> None:  # type: ignore[no-untyped-def]
    migrations = load_migrations()
    assert len(migrations) >= 2
    path = tmp_path / "live.sqlite"
    first = open_database(path, migrations=migrations[:1])
    assert isinstance(first, Ok)
    first.value.close()

    hook = PreMigrationBackup(path, backup_dir)
    result = open_database(path, on_before_migrate=hook, migrations=migrations)
    assert isinstance(result, Ok) and hook.ran
    [backup] = list_backups(backup_dir)
    assert backup.reason == "pre_migration"
    old = sqlite3.connect(backup.path)
    assert old.execute("PRAGMA user_version").fetchone()[0] == 1
    old.close()
    assert schema_version(result.value) == len(migrations)
    result.value.close()


def test_failed_pre_migration_backup_aborts_the_upgrade(
    tmp_path, backup_dir, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    migrations = load_migrations()
    path = tmp_path / "live.sqlite"
    first = open_database(path, migrations=migrations[:1])
    assert isinstance(first, Ok)
    first.value.close()

    monkeypatch.setattr(
        backups,
        "create_backup",
        lambda *a, **k: Err(BackupError("failed", "disk full")),
    )
    hook = PreMigrationBackup(path, backup_dir)
    result = open_database(path, on_before_migrate=hook, migrations=migrations)
    assert isinstance(result, Err) and result.error.code == "migration_failed"
    assert "disk full" in result.error.message and not hook.ran

    raw = sqlite3.connect(path)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 1
    raw.close()
