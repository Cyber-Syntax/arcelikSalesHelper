import sqlite3
from decimal import Decimal as D
from typing import Any

import pytest

from arcelikSalesHelper.domain.products import ProductDraft
from arcelikSalesHelper.domain.result import Err, Ok
from arcelikSalesHelper.infrastructure.repositories import ProductRepository

from .conftest import FakeClock


def draft(
    name: str = "Fridge",
    regular: str = "5000",
    website: str = "4000",
    **kw: Any,
):  # type: ignore[no-untyped-def]
    return ProductDraft(name, D(regular), D(website), **kw)


def ok(result: Any) -> Any:
    assert isinstance(result, Ok), result
    return result.value


def err(result: Any) -> Any:
    assert isinstance(result, Err), result
    return result.error


def history(db: sqlite3.Connection, product_id: int) -> list[tuple[D, D]]:
    rows = db.execute(
        "SELECT regular_price, website_price FROM pricing_history WHERE product_id = ? ORDER BY id",
        (product_id,),
    )
    return [(D(r[0]), D(r[1])) for r in rows]


# ---- add / get ------------------------------------------------------------


def test_add_and_get_roundtrip_is_exact(repo: ProductRepository) -> None:
    p = ok(
        repo.add(
            draft(
                regular="153345.56",
                website="0.10",
                default_gift_name=" Vacuum ",
            )
        )
    )
    assert p.regular_price == D("153345.56")
    assert p.website_price == D("0.10")
    assert p.default_gift_name == "Vacuum"
    assert p.archived is False
    assert p.created_at == p.updated_at == "2026-01-01T12:00:00Z"
    assert repo.get(p.id) == p


def test_get_missing_returns_none(repo: ProductRepository) -> None:
    assert repo.get(404) is None


def test_add_rejects_invalid_input_with_details(
    repo: ProductRepository,
) -> None:
    e = err(repo.add(draft(name="  ", regular="-1")))
    assert e.code == "invalid"
    assert {d.code for d in e.details} == {
        "name_required",
        "regular_price_invalid",
    }


def test_add_duplicate_name_is_case_and_whitespace_insensitive(
    repo: ProductRepository,
) -> None:
    ok(repo.add(draft("Çamaşır  Makinesi")))
    assert err(repo.add(draft(" çamaşır makinesi "))).code == "duplicate_name"


def test_add_writes_initial_pricing_history(
    repo: ProductRepository, db: sqlite3.Connection
) -> None:
    p = ok(repo.add(draft()))
    assert history(db, p.id) == [(D(5000), D(4000))]


# ---- update ---------------------------------------------------------------


def test_update_price_appends_history(
    repo: ProductRepository, db: sqlite3.Connection
) -> None:
    p = ok(repo.add(draft()))
    u = ok(repo.update(p.id, draft(website="3500")))
    assert u.website_price == D(3500)
    assert history(db, p.id) == [(D(5000), D(4000)), (D(5000), D(3500))]


def test_update_without_price_change_writes_no_history(
    repo: ProductRepository, db: sqlite3.Connection, clock: FakeClock
) -> None:
    p = ok(repo.add(draft()))
    clock.advance()
    u = ok(repo.update(p.id, draft(notes="check warranty")))
    assert u.notes == "check warranty"
    assert u.updated_at > p.updated_at
    assert len(history(db, p.id)) == 1


def test_update_with_identical_values_is_a_noop(
    repo: ProductRepository, clock: FakeClock
) -> None:
    p = ok(repo.add(draft()))
    clock.advance()
    u = ok(
        repo.update(p.id, draft(regular="5000.00", website="4000.0"))
    )  # same values, new scale
    assert u == p  # nothing written, updated_at untouched


def test_update_unknown_product(repo: ProductRepository) -> None:
    assert err(repo.update(404, draft())).code == "not_found"


def test_update_rename_to_existing_name_is_rejected(
    repo: ProductRepository,
) -> None:
    ok(repo.add(draft("A")))
    b = ok(repo.add(draft("B")))
    assert err(repo.update(b.id, draft("a"))).code == "duplicate_name"


def test_update_may_change_only_the_case_of_its_own_name(
    repo: ProductRepository,
) -> None:
    p = ok(repo.add(draft("fridge")))
    assert ok(repo.update(p.id, draft("FRIDGE"))).name == "FRIDGE"


def test_failed_history_insert_rolls_back_the_price_update(
    repo: ProductRepository, db: sqlite3.Connection
) -> None:
    p = ok(repo.add(draft()))
    db.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON pricing_history "
        "BEGIN SELECT RAISE(ABORT, 'boom'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        repo.update(p.id, draft(website="3000"))
    assert repo.get(p.id) == p
    assert not db.in_transaction


# ---- archive / restore ----------------------------------------------------


def test_archive_and_restore(repo: ProductRepository) -> None:
    p = ok(repo.add(draft()))
    assert ok(repo.archive(p.id)).archived is True
    assert ok(repo.archive(p.id)).archived is True  # idempotent
    assert ok(repo.restore(p.id)).archived is False


def test_archived_name_can_be_reused_but_blocks_restore(
    repo: ProductRepository,
) -> None:
    old = ok(repo.add(draft("Fridge")))
    ok(repo.archive(old.id))
    new = ok(repo.add(draft("fridge")))  # allowed: the old one is archived
    assert err(repo.restore(old.id)).code == "name_collision"
    ok(repo.archive(new.id))
    assert ok(repo.restore(old.id)).archived is False


def test_archived_product_can_still_be_updated(
    repo: ProductRepository,
) -> None:
    p = ok(repo.add(draft()))
    ok(repo.archive(p.id))
    u = ok(repo.update(p.id, draft(website="3900")))
    assert u.archived is True and u.website_price == D(3900)


def test_archive_unknown_product(repo: ProductRepository) -> None:
    assert err(repo.archive(404)).code == "not_found"
    assert err(repo.restore(404)).code == "not_found"


# ---- search ---------------------------------------------------------------


def test_search_is_case_insensitive_substring_and_hides_archived(
    repo: ProductRepository,
) -> None:
    a = ok(repo.add(draft("Arçelik Fridge")))
    ok(repo.add(draft("Washer")))
    archived = ok(repo.add(draft("Old Fridge")))
    ok(repo.archive(archived.id))

    assert [p.id for p in repo.search("FRIDGE")] == [a.id]
    assert {p.name for p in repo.search("fridge", include_archived=True)} == {
        "Arçelik Fridge",
        "Old Fridge",
    }
    assert len(repo.search("")) == 2


def test_search_escapes_like_wildcards(repo: ProductRepository) -> None:
    ok(repo.add(draft("50% Fridge")))
    ok(repo.add(draft("500 Fridge")))
    ok(repo.add(draft("a_b")))
    ok(repo.add(draft("axb")))
    assert [p.name for p in repo.search("50%")] == ["50% Fridge"]
    assert [p.name for p in repo.search("a_b")] == ["a_b"]
    assert repo.search("\\") == []
