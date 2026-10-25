import sqlite3
from decimal import Decimal as D
from pathlib import Path

import pytest

from arcelikSalesHelper.domain.products import ProductDraft
from arcelikSalesHelper.domain.result import Err, Ok
from arcelikSalesHelper.domain.stock import StockSource, parse_quantity
from arcelikSalesHelper.infrastructure.database import load_migrations, open_database

from .conftest import FakeClock


def product(repo):  # type: ignore[no-untyped-def]
    result = repo.add(ProductDraft("Fridge", D("5000"), D("4000")))
    assert isinstance(result, Ok)
    return result.value


def stock_rows(db: sqlite3.Connection) -> list[tuple]:  # type: ignore[type-arg]
    return [
        tuple(r)
        for r in db.execute(
            "SELECT quantity, previous_quantity, source, note FROM stock_history ORDER BY id"
        )
    ]


@pytest.mark.parametrize(
    "text, expected", [("0", 0), ("12", 12), (" 7 ", 7), ("007", 7), ("1000000", 1_000_000)]
)
def test_parse_quantity_accepts(text: str, expected: int) -> None:
    assert parse_quantity(text) == Ok(expected)


@pytest.mark.parametrize(
    "text", ["", "  ", "-1", "1.5", "1,5", "1.000", "abc", "１２", "1000001", "9" * 5000]
)
def test_parse_quantity_rejects(text: str) -> None:
    assert isinstance(parse_quantity(text), Err)


def test_new_products_have_no_count(repo) -> None:  # type: ignore[no-untyped-def]
    p = product(repo)
    assert p.quantity is None and p.quantity_updated_at is None


def test_set_quantity_records_value_time_and_history(repo, db, clock: FakeClock) -> None:  # type: ignore[no-untyped-def]
    p = product(repo)
    clock.advance(60)
    first = repo.set_quantity(p.id, 5, StockSource.MANUAL, "  photo  ")
    assert isinstance(first, Ok)
    assert first.value.quantity == 5
    assert first.value.quantity_updated_at == "2026-01-01T12:01:00Z"
    assert first.value.updated_at == p.updated_at  # product data untouched
    repo.set_quantity(p.id, 3, StockSource.CSV)
    assert stock_rows(db) == [(5, None, "manual", "photo"), (3, 5, "csv", None)]


def test_the_same_quantity_is_recorded_again_and_refreshes_the_time(repo, db, clock) -> None:  # type: ignore[no-untyped-def]
    p = product(repo)
    repo.set_quantity(p.id, 5, StockSource.MANUAL)
    clock.advance(3600)
    again = repo.set_quantity(p.id, 5, StockSource.MANUAL)
    assert isinstance(again, Ok) and again.value.quantity_updated_at == "2026-01-01T13:00:00Z"
    assert len(stock_rows(db)) == 2


def test_set_quantity_errors(repo) -> None:  # type: ignore[no-untyped-def]
    p = product(repo)
    missing = repo.set_quantity(404, 1, StockSource.MANUAL)
    assert isinstance(missing, Err) and missing.error.code == "not_found"
    for bad in (-1, 1_000_001):
        result = repo.set_quantity(p.id, bad, StockSource.MANUAL)
        assert isinstance(result, Err) and result.error.code == "invalid"
    assert repo.get(p.id).quantity is None  # type: ignore[union-attr]


def test_archived_products_can_be_counted(repo) -> None:  # type: ignore[no-untyped-def]
    p = product(repo)
    repo.archive(p.id)
    assert isinstance(repo.set_quantity(p.id, 2, StockSource.MANUAL), Ok)


def test_editing_a_product_keeps_its_count(repo) -> None:  # type: ignore[no-untyped-def]
    p = product(repo)
    repo.set_quantity(p.id, 9, StockSource.MANUAL)
    updated = repo.update(p.id, ProductDraft("Fridge", D("5000"), D("3500"), "Gift", "n"))
    assert isinstance(updated, Ok) and updated.value.quantity == 9


def test_stock_history_is_immutable_and_constrained(repo, db) -> None:  # type: ignore[no-untyped-def]
    p = product(repo)
    repo.set_quantity(p.id, 1, StockSource.MANUAL)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute("UPDATE stock_history SET quantity = 2")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute("DELETE FROM stock_history")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO stock_history (product_id, quantity, source, changed_at) "
            "VALUES (?, 1, 'robot', 't')",
            (p.id,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO stock_history (product_id, quantity, source, changed_at) "
            "VALUES (999, 1, 'manual', 't')"
        )


def test_upgrade_from_v2_keeps_products_and_leaves_counts_unknown(tmp_path: Path) -> None:
    migrations = load_migrations()
    assert len(migrations) >= 3
    path = tmp_path / "a.sqlite"
    old = open_database(path, migrations=migrations[:2])
    assert isinstance(old, Ok)
    old.value.execute(
        "INSERT INTO products (name, name_key, regular_price, website_price, created_at, "
        "updated_at) VALUES ('Fridge', 'fridge', '5000', '4000', 't', 't')"
    )
    old.value.close()

    new = open_database(path, migrations=migrations)
    assert isinstance(new, Ok)
    row = new.value.execute("SELECT name, quantity, quantity_updated_at FROM products").fetchone()
    assert tuple(row) == ("Fridge", None, None)
    new.value.close()