import sqlite3
from pathlib import Path

import pytest

from arcelikSalesHelper.domain.result import Err, Ok
from arcelikSalesHelper.infrastructure.database import (
    Migration,
    load_migrations,
    open_database,
    schema_version,
    transaction,
)

M1 = Migration(1, "one", "CREATE TABLE a (x INTEGER);")
M2 = Migration(2, "two", "CREATE TABLE b (y INTEGER);")
BAD2 = Migration(
    2, "bad", "CREATE TABLE c (z INTEGER); INSERT INTO missing VALUES (1);"
)


def test_upgrade_from_v1_adds_entered_text_column(tmp_path: Path) -> None:
    migrations = load_migrations()
    assert len(migrations) >= 2
    path = tmp_path / "a.sqlite"
    open_ok(path, migrations=migrations[:1]).close()

    calls: list[tuple[int, int]] = []
    conn = open_ok(
        path,
        on_before_migrate=lambda f, t: calls.append((f, t)),
        migrations=migrations,
    )
    assert calls == [(1, len(migrations))]  # the pre-migration hook ran
    columns = {
        r["name"] for r in conn.execute("PRAGMA table_info(calculation_lines)")
    }
    assert "entered_json" in columns
    conn.close()


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {r["name"] for r in rows}


def open_ok(path: Path, **kwargs):  # type: ignore[no-untyped-def]
    result = open_database(path, **kwargs)
    assert isinstance(result, Ok), result
    return result.value


# ---- migrations -----------------------------------------------------------


def test_packaged_migrations_are_contiguous() -> None:
    versions = [m.version for m in load_migrations()]
    assert versions and versions == list(range(1, len(versions) + 1))


def test_fresh_database_is_fully_migrated(db: sqlite3.Connection) -> None:
    assert schema_version(db) == len(load_migrations())
    assert {
        "app_metadata",
        "products",
        "pricing_history",
        "calculation_snapshots",
        "calculation_lines",
    } <= table_names(db)
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_reopening_a_current_database_does_not_request_a_backup(
    tmp_path: Path,
) -> None:
    path = tmp_path / "a.sqlite"
    open_ok(path).close()
    calls: list[tuple[int, int]] = []
    open_ok(path, on_before_migrate=lambda f, t: calls.append((f, t))).close()
    assert calls == []


def test_fresh_database_does_not_request_a_pre_migration_backup(
    tmp_path: Path,
) -> None:
    calls: list[tuple[int, int]] = []
    open_ok(
        tmp_path / "a.sqlite",
        on_before_migrate=lambda f, t: calls.append((f, t)),
    ).close()
    assert calls == []


def test_pre_migration_callback_is_called_before_upgrading(
    tmp_path: Path,
) -> None:
    path = tmp_path / "a.sqlite"
    open_ok(path, migrations=(M1,)).close()

    seen: list[tuple[int, int, int]] = []
    probe = sqlite3.connect(path)

    def callback(frm: int, to: int) -> None:
        seen.append(
            (frm, to, probe.execute("PRAGMA user_version").fetchone()[0])
        )

    conn = open_ok(path, on_before_migrate=callback, migrations=(M1, M2))
    probe.close()
    assert seen == [(1, 2, 1)]  # still at version 1 when the callback ran
    assert schema_version(conn) == 2
    assert "b" in table_names(conn)
    conn.close()


def test_failing_pre_migration_callback_aborts_the_upgrade(
    tmp_path: Path,
) -> None:
    path = tmp_path / "a.sqlite"
    open_ok(path, migrations=(M1,)).close()

    def boom(frm: int, to: int) -> None:
        raise RuntimeError("disk full")

    result = open_database(path, on_before_migrate=boom, migrations=(M1, M2))
    assert isinstance(result, Err)
    assert result.error.code == "migration_failed"
    assert "disk full" in result.error.message

    conn = open_ok(path, migrations=(M1,))
    assert schema_version(conn) == 1
    assert "b" not in table_names(conn)
    conn.close()


def test_failed_migration_rolls_back_schema_and_version(
    tmp_path: Path,
) -> None:
    path = tmp_path / "a.sqlite"
    open_ok(path, migrations=(M1,)).close()

    result = open_database(path, migrations=(M1, BAD2))
    assert isinstance(result, Err)
    assert result.error.code == "migration_failed"

    conn = open_ok(path, migrations=(M1,))
    assert schema_version(conn) == 1
    assert "c" not in table_names(conn)
    conn.close()


def test_newer_schema_is_refused_and_left_untouched(tmp_path: Path) -> None:
    path = tmp_path / "a.sqlite"
    conn = open_ok(path)
    conn.execute("PRAGMA user_version = 99")
    conn.close()

    result = open_database(path)
    assert isinstance(result, Err)
    assert result.error.code == "schema_too_new"
    assert "daha yeni bir sürümüyle" in result.error.message

    raw = sqlite3.connect(path)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 99
    raw.close()


def test_non_database_file_is_a_typed_error(tmp_path: Path) -> None:
    path = tmp_path / "garbage.sqlite"
    path.write_bytes(b"this is definitely not a sqlite database" * 100)
    result = open_database(path)
    assert isinstance(result, Err)
    assert result.error.code == "open_failed"


# ---- transaction helper ---------------------------------------------------


def test_transaction_rolls_back_on_exception(db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError), transaction(db):
        db.execute("INSERT INTO app_metadata VALUES ('k', 'v')")
        raise ValueError
    assert (
        db.execute("SELECT 1 FROM app_metadata WHERE key = 'k'").fetchone()
        is None
    )
    assert not db.in_transaction


def test_nested_transaction_joins_the_outer_one(
    db: sqlite3.Connection,
) -> None:
    with pytest.raises(ValueError), transaction(db):
        with transaction(db):
            db.execute("INSERT INTO app_metadata VALUES ('k', 'v')")
        assert db.in_transaction  # inner exit did not commit
        raise ValueError
    assert (
        db.execute("SELECT 1 FROM app_metadata WHERE key = 'k'").fetchone()
        is None
    )


# ---- schema constraints ---------------------------------------------------


def seed(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO products (id, name, name_key, regular_price, website_price, "
        "created_at, updated_at) VALUES (1, 'Fridge', 'fridge', '5000', '4000', 't', 't')"
    )
    conn.execute(
        "INSERT INTO pricing_history (product_id, regular_price, website_price, changed_at) "
        "VALUES (1, '5000', '4000', 't')"
    )
    conn.execute(
        "INSERT INTO calculation_snapshots (id, created_at, app_version, schema_version, "
        "totals_json, confirmation_state, warnings_json) "
        "VALUES (1, 't', '0.1.0', 1, '{}', 'pos_unverified', '[]')"
    )
    conn.execute(
        "INSERT INTO calculation_lines (snapshot_id, line_index, product_id, product_name, "
        "quantity, regular_price, website_price, coupon, effective_website_unit, "
        "gift_selected, result_json) "
        "VALUES (1, 0, 1, 'Fridge', 1, '5000', '4000', '0', '4000', 0, '{}')"
    )


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE calculation_snapshots SET app_version = 'x'",
        "DELETE FROM calculation_snapshots",
        "UPDATE calculation_lines SET product_name = 'x'",
        "DELETE FROM calculation_lines",
        "UPDATE pricing_history SET regular_price = '1'",
        "DELETE FROM pricing_history",
    ],
)
def test_history_tables_are_immutable(
    db: sqlite3.Connection, sql: str
) -> None:
    seed(db)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute(sql)


def test_snapshot_lines_require_an_existing_snapshot(
    db: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO calculation_lines (snapshot_id, line_index, product_name, quantity, "
            "regular_price, website_price, coupon, effective_website_unit, gift_selected, "
            "result_json) VALUES (42, 0, 'X', 1, '1', '1', '0', '1', 0, '{}')"
        )


def test_snapshot_lines_do_not_depend_on_live_products(
    db: sqlite3.Connection,
) -> None:
    db.execute(
        "INSERT INTO calculation_snapshots (id, created_at, app_version, schema_version, "
        "totals_json, warnings_json) VALUES (1, 't', '0.1.0', 1, '{}', '[]')"
    )
    db.execute(
        "INSERT INTO calculation_lines (snapshot_id, line_index, product_id, product_name, "
        "quantity, regular_price, website_price, coupon, effective_website_unit, "
        "gift_selected, result_json) VALUES (1, 0, 999, 'Gone', 1, '1', '1', '0', '1', 0, '{}')"
    )  # product_id 999 does not exist: informational only


def test_pricing_history_requires_an_existing_product(
    db: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO pricing_history (product_id, regular_price, website_price, changed_at) "
            "VALUES (999, '1', '1', 't')"
        )
