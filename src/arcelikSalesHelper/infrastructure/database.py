from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from arcelikSalesHelper.domain.result import Err, Ok, Result

_MIGRATION_FILE = re.compile(r"(\d{4})_([A-Za-z0-9_]+)\.sql")

# (from_version, to_version). Must raise if the backup could not be made;
# raising aborts the migration.
BeforeMigrate = Callable[[int, int], None]


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


@dataclass(frozen=True)
class DbOpenError:
    code: str  # open_failed | schema_too_new | migration_failed
    message: str


class MigrationError(Exception):
    pass


class SchemaTooNewError(Exception):
    def __init__(self, db_version: int, app_version: int) -> None:
        super().__init__(f"database schema {db_version} is newer than supported {app_version}")
        self.db_version = db_version
        self.app_version = app_version


# --------------------------------------------------------------------------
# connection / transactions
# --------------------------------------------------------------------------


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a connection with the project pragmas.

    ``isolation_level=None`` disables the sqlite3 module's implicit transaction
    handling; every write goes through ``transaction()``.
    """
    conn = sqlite3.connect(str(path), isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.Error:
        conn.close()
        raise
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT, rolling back on any exception.

    If a transaction is already open, join it: the outermost caller decides
    commit/rollback. M7 relies on this to apply a whole import atomically.
    """
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


# --------------------------------------------------------------------------
# migrations
# --------------------------------------------------------------------------


def load_migrations() -> tuple[Migration, ...]:
    root = resources.files("arcelikSalesHelper.infrastructure").joinpath("migrations")
    found: list[Migration] = []
    for entry in root.iterdir():
        match = _MIGRATION_FILE.fullmatch(entry.name)
        if match:
            found.append(
                Migration(int(match[1]), match[2], entry.read_text(encoding="utf-8"))
            )
    found.sort(key=lambda m: m.version)
    _check_contiguous(found)
    return tuple(found)


def _check_contiguous(migrations: Sequence[Migration]) -> None:
    versions = [m.version for m in migrations]
    if versions != list(range(1, len(versions) + 1)):
        raise MigrationError(f"Migration versions must be 1..N without gaps, got {versions}")


def schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _apply(conn: sqlite3.Connection, migration: Migration) -> None:
    # DDL is transactional in SQLite, and so is PRAGMA user_version, so a
    # failure anywhere in the script leaves schema and version untouched.
    script = (
        "BEGIN IMMEDIATE;\n"
        f"{migration.sql}\n"
        f"PRAGMA user_version = {migration.version};\n"
        "COMMIT;"
    )
    try:
        conn.executescript(script)
    except sqlite3.Error as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise MigrationError(
            f"Migration {migration.version:04d}_{migration.name} failed: {exc}"
        ) from exc


def migrate(
    conn: sqlite3.Connection,
    migrations: Sequence[Migration],
    on_before_migrate: BeforeMigrate | None = None,
) -> tuple[int, ...]:
    """Apply pending migrations, each in its own transaction. Returns applied versions."""
    _check_contiguous(migrations)
    current = schema_version(conn)
    latest = migrations[-1].version if migrations else 0
    if current > latest:
        raise SchemaTooNewError(current, latest)

    pending = [m for m in migrations if m.version > current]
    if not pending:
        return ()

    # A brand-new database (version 0) has nothing worth backing up; the M6
    # baseline backup runs after the initial schema exists.
    if on_before_migrate is not None and current > 0:
        try:
            on_before_migrate(current, latest)
        except Exception as exc:
            raise MigrationError(f"Pre-migration backup failed: {exc}") from exc

    applied: list[int] = []
    for migration in pending:
        _apply(conn, migration)
        applied.append(migration.version)
    return tuple(applied)


def open_database(
    path: Path | str,
    on_before_migrate: BeforeMigrate | None = None,
    migrations: Sequence[Migration] | None = None,
) -> Result[sqlite3.Connection, DbOpenError]:
    migs = load_migrations() if migrations is None else tuple(migrations)
    try:
        conn = connect(path)
    except sqlite3.Error as exc:
        return Err(DbOpenError("open_failed", f"Cannot open the database: {exc}"))
    try:
        migrate(conn, migs, on_before_migrate)
    except SchemaTooNewError as exc:
        conn.close()
        return Err(
            DbOpenError(
                "schema_too_new",
                f"This database was created by a newer version of the application "
                f"(schema {exc.db_version}; this version supports up to {exc.app_version}). "
                f"Update the application. The database has not been modified.",
            )
        )
    except MigrationError as exc:
        conn.close()
        return Err(DbOpenError("migration_failed", str(exc)))
    except sqlite3.Error as exc:
        conn.close()
        return Err(DbOpenError("open_failed", f"Cannot open the database: {exc}"))
    return Ok(conn)