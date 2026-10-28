"""Verified backups of the live database.

A backup is only ever visible under its final name after it was written with the
SQLite backup API, reopened read-only, passed ``PRAGMA integrity_check`` and had
the same ``user_version`` as the live database. Rotation runs only after that,
and only touches files matching the backup naming pattern.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TypeAlias

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.constants import BACKUP_PREFIX
from arcelikSalesHelper.domain.result import Err, Ok, Result

from .database import connect, schema_version, transaction
from .repositories import utc_now

log = logging.getLogger(__name__)

KEEP_VERIFIED_BACKUPS = 30
STARTUP_MAX_AGE = timedelta(hours=24)
_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
_ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_STALE_TMP_SECONDS = 3600
_FINAL_NAME = re.compile(
    rf"{re.escape(BACKUP_PREFIX)}-(\d{{8}}T\d{{6}}Z)-([a-z_]+)(?:-(\d+))?\.sqlite"
)

_K_SUCCESS_AT = "last_backup_success_at"
_K_SUCCESS_PATH = "last_backup_path"
_K_FAIL_AT = "last_backup_failure_at"
_K_FAIL_REASON = "last_backup_failure_reason"
_K_FAIL_MESSAGE = "last_backup_failure_message"


class BackupReason(Enum):
    BASELINE = "baseline"
    STARTUP = "startup"
    CLOSE = "close"
    PRE_MIGRATION = "pre_migration"
    PRE_IMPORT = "pre_import"  # used by M7
    MANUAL = "manual"


@dataclass(frozen=True)
class BackupError:
    code: str  # busy | failed | verification_failed
    message: str


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    created_at: datetime
    reason: BackupReason
    size_bytes: int
    deleted: tuple[Path, ...] = ()
    rotation_errors: tuple[str, ...] = ()


BackupResult: TypeAlias = Result[BackupInfo, BackupError]


@dataclass(frozen=True)
class BackupFile:
    path: Path
    created_at: datetime
    reason: str
    counter: int

    @property
    def created_at_iso(self) -> str:
        return self.created_at.strftime(_ISO_FORMAT)


@dataclass(frozen=True)
class BackupFailure:
    at: str  # UTC ISO-8601
    reason: str
    message: str


@dataclass(frozen=True)
class BackupStatus:
    latest: BackupFile | None
    count: int
    failure: BackupFailure | None


# --------------------------------------------------------------------------
# pure policy
# --------------------------------------------------------------------------


def needs_startup_backup(last_success: datetime | None, now: datetime) -> bool:
    """No backup yet, or the latest one is strictly older than 24 hours.

    A latest backup dated in the future means the clock moved back; it cannot
    be trusted, so a new backup is made.
    """
    if last_success is None or last_success > now:
        return True
    return now - last_success > STARTUP_MAX_AGE


def needs_close_backup(db_changed: bool) -> bool:
    return db_changed


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------


def list_backups(backup_dir: Path) -> list[BackupFile]:
    """Verified backups, newest first. Only files matching the naming pattern count."""
    try:
        entries = list(backup_dir.iterdir())
    except OSError:
        return []
    found: list[BackupFile] = []
    for entry in entries:
        match = _FINAL_NAME.fullmatch(entry.name)
        if match is None or not entry.is_file():
            continue
        try:
            created = datetime.strptime(match[1], _STAMP_FORMAT).replace(
                tzinfo=UTC
            )
        except ValueError:
            continue
        found.append(BackupFile(entry, created, match[2], int(match[3] or 0)))
    found.sort(
        key=lambda b: (b.created_at, b.counter, b.path.name), reverse=True
    )
    return found


def _final_path(backup_dir: Path, stamp: str, reason: BackupReason) -> Path:
    base = f"{BACKUP_PREFIX}-{stamp}-{reason.value}"
    candidate = backup_dir / f"{base}.sqlite"
    counter = 0
    while candidate.exists():
        counter += 1
        candidate = backup_dir / f"{base}-{counter}.sqlite"
    return candidate


def _discard(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        with suppress(OSError):
            Path(f"{path}{suffix}").unlink()


def _remove_stale_temp_files(backup_dir: Path) -> None:
    cutoff = time.time() - _STALE_TMP_SECONDS
    for entry in backup_dir.glob(".tmp-*"):
        with suppress(OSError):
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()


def _fsync(path: Path) -> None:
    with open(path, "r+b") as handle:  # r+ so Windows allows FlushFileBuffers
        os.fsync(handle.fileno())


def _fsync_dir(directory: Path) -> None:
    if os.name != "posix":
        return  # directories cannot be opened for fsync on Windows
    with suppress(OSError):
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _unlink(path: Path) -> None:
    path.unlink()


def rotate_backups(
    backup_dir: Path, keep: int, protect: Path | None = None
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    """Delete verified backups beyond the newest ``keep``. Returns (deleted, errors).

    Only files matching the backup naming pattern are considered, so the live
    database and unrelated files are never touched.
    """
    if keep < 1:
        raise ValueError("keep must be at least 1")
    deleted: list[Path] = []
    errors: list[str] = []
    for old in list_backups(backup_dir)[keep:]:
        if protect is not None and old.path == protect:
            continue
        try:
            _unlink(old.path)
            deleted.append(old.path)
        except OSError as exc:
            log.warning("Could not delete old backup %s: %s", old.path, exc)
            errors.append(f"{old.path.name}: {exc}")
    return tuple(deleted), tuple(errors)


# --------------------------------------------------------------------------
# creating and verifying
# --------------------------------------------------------------------------


def _copy(live_conn: sqlite3.Connection, tmp: Path) -> None:
    _discard(tmp)
    dest = sqlite3.connect(str(tmp))
    try:
        live_conn.backup(dest)
        # The copy inherits the WAL flag from the source. Switch it to a plain
        # rollback journal so the backup is one self-contained file.
        dest.execute("PRAGMA journal_mode=DELETE")
    finally:
        dest.close()


def verify_backup_file(
    path: Path, expected_user_version: int
) -> Result[None, str]:
    try:
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return Err(T.backup_cannot_open_copy(str(exc)))
    try:
        rows = [
            str(r[0])
            for r in conn.execute("PRAGMA integrity_check").fetchall()
        ]
        if rows != ["ok"]:
            return Err(T.backup_integrity("; ".join(rows[:3])))
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version != expected_user_version:
            return Err(
                T.backup_version_mismatch(version, expected_user_version)
            )
        return Ok(None)
    except sqlite3.Error as exc:
        return Err(str(exc))
    finally:
        conn.close()


def create_backup(
    live_conn: sqlite3.Connection,
    backup_dir: Path,
    reason: BackupReason,
    *,
    now: datetime | None = None,
    keep: int = KEEP_VERIFIED_BACKUPS,
) -> BackupResult:
    """Create, verify and publish one backup, then rotate. Never raises for I/O or SQLite errors."""
    moment = (now or utc_now()).astimezone(UTC)
    stamp = moment.strftime(_STAMP_FORMAT)
    tmp = backup_dir / f".tmp-{stamp}-{os.getpid()}.sqlite"
    try:
        if live_conn.in_transaction:
            return Err(
                BackupError(
                    "busy",
                    T.BACKUP_BUSY,
                )
            )
        backup_dir.mkdir(parents=True, exist_ok=True)
        _remove_stale_temp_files(backup_dir)
        expected_version = schema_version(live_conn)
        _copy(live_conn, tmp)
        verified = verify_backup_file(tmp, expected_version)
        if isinstance(verified, Err):
            _discard(tmp)
            return Err(
                BackupError(
                    "verification_failed",
                    T.backup_verification_failed(verified.error),
                )
            )
        _fsync(tmp)
        final = _final_path(backup_dir, stamp, reason)
        os.replace(tmp, final)
        _fsync_dir(backup_dir)
        size = final.stat().st_size
    except (sqlite3.Error, OSError) as exc:
        _discard(tmp)
        return Err(BackupError("failed", T.backup_failed_create(str(exc))))

    # Only now, with a new verified backup in place, is anything old removed.
    deleted, rotation_errors = rotate_backups(backup_dir, keep, protect=final)
    return Ok(
        BackupInfo(final, moment, reason, size, deleted, rotation_errors)
    )


# --------------------------------------------------------------------------
# outcome bookkeeping (app_metadata)
# --------------------------------------------------------------------------


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(_ISO_FORMAT)


def _set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_metadata (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def record_success(conn: sqlite3.Connection, info: BackupInfo) -> None:
    with transaction(conn):
        _set(conn, _K_SUCCESS_AT, _iso(info.created_at))
        _set(conn, _K_SUCCESS_PATH, str(info.path))
        conn.execute(
            "DELETE FROM app_metadata WHERE key IN (?, ?, ?)",
            (_K_FAIL_AT, _K_FAIL_REASON, _K_FAIL_MESSAGE),
        )


def record_failure(
    conn: sqlite3.Connection,
    when: datetime,
    reason: BackupReason,
    message: str,
) -> None:
    with transaction(conn):
        _set(conn, _K_FAIL_AT, _iso(when))
        _set(conn, _K_FAIL_REASON, reason.value)
        _set(conn, _K_FAIL_MESSAGE, message)


def read_failure(conn: sqlite3.Connection) -> BackupFailure | None:
    rows = conn.execute(
        "SELECT key, value FROM app_metadata WHERE key IN (?, ?, ?)",
        (_K_FAIL_AT, _K_FAIL_REASON, _K_FAIL_MESSAGE),
    )
    values = {r["key"]: r["value"] for r in rows}
    if _K_FAIL_AT not in values:
        return None
    return BackupFailure(
        values[_K_FAIL_AT],
        values.get(_K_FAIL_REASON, ""),
        values.get(_K_FAIL_MESSAGE, ""),
    )


# --------------------------------------------------------------------------
# manager
# --------------------------------------------------------------------------


class BackupManager:
    """Runs backups for one live connection and keeps the outcome bookkeeping.

    "Database changed" means ``conn.total_changes`` moved since the last
    successful backup. The bookkeeping writes of a *successful* backup are
    excluded, so a backup never makes the database look dirty by itself.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        backup_dir: Path,
        clock: Callable[[], datetime] = utc_now,
        keep: int = KEEP_VERIFIED_BACKUPS,
    ) -> None:
        self._conn = conn
        self._dir = backup_dir
        self._clock = clock
        self._keep = keep
        self._baseline = conn.total_changes
        self._forced_dirty = False

    @property
    def backup_dir(self) -> Path:
        return self._dir

    def mark_dirty(self) -> None:
        """For changes made before this manager existed (a migration)."""
        self._forced_dirty = True

    def has_changes(self) -> bool:
        return self._forced_dirty or self._conn.total_changes != self._baseline

    def run(self, reason: BackupReason) -> BackupResult:
        moment = self._clock()
        result = create_backup(
            self._conn, self._dir, reason, now=moment, keep=self._keep
        )
        try:
            match result:
                case Ok(info):
                    record_success(self._conn, info)
                case Err(error):
                    log.error(
                        "Backup (%s) failed: %s", reason.value, error.message
                    )
                    record_failure(self._conn, moment, reason, error.message)
        except sqlite3.Error:
            log.exception("Could not record the backup outcome")
        if isinstance(result, Ok):
            self._baseline = self._conn.total_changes
            self._forced_dirty = False
        return result

    def latest(self) -> BackupFile | None:
        files = list_backups(self._dir)
        return files[0] if files else None

    def run_startup_backup_if_needed(self) -> BackupResult | None:
        latest = self.latest()
        last = None if latest is None else latest.created_at
        if needs_startup_backup(last, self._clock()):
            return self.run(BackupReason.STARTUP)
        return None

    def run_close_backup_if_needed(self) -> BackupResult | None:
        if needs_close_backup(self.has_changes()):
            return self.run(BackupReason.CLOSE)
        return None

    def status(self) -> BackupStatus:
        files = list_backups(self._dir)
        failure: BackupFailure | None = None
        try:
            failure = read_failure(self._conn)
        except sqlite3.Error:
            log.exception("Could not read the backup failure state")
        return BackupStatus(files[0] if files else None, len(files), failure)


class PreMigrationBackup:
    """``on_before_migrate`` callback for ``open_database``.

    The callback receives no connection, so it opens its own to the same file.
    Raising aborts the migration (database.migrate wraps it as migration_failed).
    """

    def __init__(
        self,
        db_path: Path,
        backup_dir: Path,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._db_path = db_path
        self._backup_dir = backup_dir
        self._clock = clock
        self.ran = False

    def __call__(self, from_version: int, to_version: int) -> None:
        conn = connect(self._db_path)
        try:
            result = create_backup(
                conn,
                self._backup_dir,
                BackupReason.PRE_MIGRATION,
                now=self._clock(),
            )
        finally:
            conn.close()
        if isinstance(result, Err):
            raise RuntimeError(result.error.message)
        self.ran = True
