import sqlite3
from dataclasses import replace
from decimal import Decimal as D

import pytest

from arcelikSalesHelper.application.calculator import evaluate_transaction
from arcelikSalesHelper.application.history import (
    SnapshotRecord,
    build_snapshot,
)
from arcelikSalesHelper.domain.models import PosCalculationMode
from arcelikSalesHelper.domain.products import ProductDraft
from arcelikSalesHelper.domain.result import Ok
from arcelikSalesHelper.infrastructure.history_repository import (
    HistoryRepository,
)
from arcelikSalesHelper.infrastructure.repositories import ProductRepository

from .test_transaction_app import form, two_forms


def make_record(
    forms=None, created_at: str = "2026-01-01T12:00:00Z"
) -> SnapshotRecord:  # type: ignore[no-untyped-def]
    ev = evaluate_transaction(two_forms() if forms is None else forms)
    built = build_snapshot(
        ev, created_at=created_at, app_version="0.1.0", schema_version=2
    )
    assert isinstance(built, Ok), built
    return built.value


def test_save_and_get_roundtrip_is_lossless(db: sqlite3.Connection) -> None:
    repo = HistoryRepository(db)
    record = make_record()
    sid = repo.save(record)
    assert repo.get(sid) == replace(record, id=sid)
    assert repo.count() == 1


def test_save_and_get_preserves_pos_calculation_mode(
    db: sqlite3.Connection,
) -> None:
    repo = HistoryRepository(db)
    record = make_record(
        [
            form(
                regular_price="38.299,00",
                website_discounted_price="34.469,10",
                manager_value="30.000,00",
                pos_calculation_mode=PosCalculationMode.PERCENTAGE,
            )
        ]
    )
    sid = repo.save(record)
    restored = repo.get(sid)
    assert restored is not None
    assert restored.lines[0].pos_calculation_mode == "percentage"


def test_get_missing_returns_none(db: sqlite3.Connection) -> None:
    assert HistoryRepository(db).get(404) is None


def test_failed_save_leaves_nothing_behind(db: sqlite3.Connection) -> None:
    repo = HistoryRepository(db)
    record = make_record()
    broken = replace(
        record, lines=(record.lines[0], record.lines[0])
    )  # duplicate line_index
    with pytest.raises(sqlite3.IntegrityError):
        repo.save(broken)
    assert repo.count() == 0
    assert (
        db.execute("SELECT COUNT(*) FROM calculation_lines").fetchone()[0] == 0
    )
    assert not db.in_transaction


def test_snapshot_survives_product_edits_and_archiving(
    db: sqlite3.Connection,
) -> None:
    products = ProductRepository(db)
    added = products.add(ProductDraft("Fridge", D(5000), D(4000)))
    assert isinstance(added, Ok)
    product = added.value

    repo = HistoryRepository(db)
    record = make_record(
        [form(product_id=product.id, manager_value="3.000,00")]
    )
    sid = repo.save(record)
    before = repo.get(sid)

    products.update(
        product.id, ProductDraft("Fridge XL", D(9000), D(8000), "Gift", "note")
    )
    products.archive(product.id)

    assert repo.get(sid) == before == replace(record, id=sid)
    assert before is not None and before.lines[0].product_id == product.id
    assert before.lines[0].product_name == "Fridge"


def test_saved_history_cannot_be_changed(db: sqlite3.Connection) -> None:
    repo = HistoryRepository(db)
    repo.save(make_record())
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute("UPDATE calculation_lines SET quantity = 9")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute("DELETE FROM calculation_snapshots")
    assert not hasattr(repo, "delete") and not hasattr(repo, "update")


def test_headers_are_newest_first_with_names_counts_and_paging(
    db: sqlite3.Connection,
) -> None:
    repo = HistoryRepository(db)
    first = repo.save(make_record())
    second = repo.save(make_record([form(product_name="Dryer")]))
    third = repo.save(make_record())

    headers = repo.list_headers(limit=2)
    assert [h.id for h in headers] == [third, second]
    assert (
        headers[1].product_names == ("Dryer",) and headers[1].line_count == 1
    )
    assert (
        headers[0].product_names == ("Fridge", "Washer")
        and headers[0].line_count == 2
    )

    older = repo.list_headers(limit=2, before_id=headers[-1].id)
    assert [h.id for h in older] == [first]
    assert repo.list_headers(limit=2, before_id=first) == []
