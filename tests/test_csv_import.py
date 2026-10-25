import sqlite3
from decimal import Decimal as D
from pathlib import Path

import pytest

from arcelikSalesHelper.domain.products import ProductDraft
from arcelikSalesHelper.domain.result import Err, Ok
from arcelikSalesHelper.infrastructure import csv_import
from arcelikSalesHelper.infrastructure.csv_import import (
    Decision,
    ImportFormat,
    Kind,
    apply_plan,
    index_products,
    parse_csv_file,
    parse_csv_text,
    plan_import,
)
from arcelikSalesHelper.infrastructure.repositories import ProductRepository

HEADER = "product_name,regular_price,website_discounted_price"
HEADER_Q = HEADER + ",quantity"


def parsed(text: str):  # type: ignore[no-untyped-def]
    result = parse_csv_text(text)
    assert isinstance(result, Ok), result
    return result.value


def plan_for(text: str, repo: ProductRepository):  # type: ignore[no-untyped-def]
    return plan_import(parsed(text), index_products(repo.search("", include_archived=True)))


def add(repo, name, regular="5000", website="4000", gift=None, notes=None):  # type: ignore[no-untyped-def]
    result = repo.add(ProductDraft(name, D(regular), D(website), gift, notes))
    assert isinstance(result, Ok), result
    return result.value


def kinds(plan) -> dict[str, Kind]:  # type: ignore[no-untyped-def]
    return {i.row.name: i.kind for i in plan.items}


def update_all(plan) -> dict[int, Decision]:  # type: ignore[no-untyped-def]
    return {i.row.row: Decision.UPDATE for i in plan.conflicts}


# ---- parsing --------------------------------------------------------------


def test_turkish_and_plain_numbers_are_both_accepted() -> None:
    p = parsed(f'{HEADER}\nFridge,"54.999,00","44.999,00"\nWasher,54999,44999.50\n')
    assert p.format is ImportFormat.PRICES and p.errors == ()
    assert [(r.row, r.name, r.regular_price, r.website_price) for r in p.rows] == [
        (2, "Fridge", D("54999"), D("44999")),
        (3, "Washer", D("54999"), D("44999.50")),
    ]


def test_utf8_bom_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "in.csv"
    path.write_bytes(b"\xef\xbb\xbf" + f"{HEADER}\nÇamaşır,1,2\n".encode())
    result = parse_csv_file(path)
    assert isinstance(result, Ok) and result.value.rows[0].name == "Çamaşır"


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("", "empty"),
        ("name,price\n", "missing"),
        (f"{HEADER},extra\n", "unexpected"),
        ("product_name,regular_price\n", "missing"),
        (f"{HEADER},{HEADER.split(',')[0]}\n", "more than once"),
        (HEADER.replace(",", ";") + "\n", "semicolon"),
    ],
)
def test_bad_headers_are_file_level_errors(text: str, fragment: str) -> None:
    result = parse_csv_text(text)
    assert isinstance(result, Err) and fragment in result.error.lower()


def test_blank_lines_are_skipped_and_errors_carry_row_and_column() -> None:
    p = parsed(f"{HEADER}\nFridge,5000,4000\n\n,5000,4000\nWasher,abc,4000\nDryer,-5,\n")
    assert [r.name for r in p.rows] == ["Fridge"] and p.blank_rows == 1
    assert [(e.row, e.column) for e in p.errors] == [
        (4, "product_name"),
        (5, "regular_price"),
        (6, "regular_price"),
        (6, "website_discounted_price"),
    ]


def test_duplicate_names_in_the_file_reference_the_first_row() -> None:
    p = parsed(f"{HEADER}\nFridge,1,1\n  fridge ,2,2\n")
    assert [r.row for r in p.rows] == [2]
    assert p.errors[0].row == 3 and "row 2" in p.errors[0].message


def test_extra_cells_are_an_error_unless_blank() -> None:
    p = parsed(f"{HEADER}\nA,1,2,3\nB,1,2,\n")
    assert [e.row for e in p.errors] == [2] and [r.name for r in p.rows] == ["B"]


def test_ambiguous_price_is_flagged_but_read_as_thousands() -> None:
    row = parsed(f"{HEADER}\nFridge,5.000,4000\n").rows[0]
    assert row.regular_price == D("5000") and len(row.warnings) == 1


def test_quantity_column_is_optional_per_row_and_validated() -> None:
    p = parsed(f"{HEADER_Q}\nA,1,1,12\nB,1,1,\nC,1,1,x\nD,1,1,-1\nE,1,1,1.5\n")
    assert [(r.name, r.quantity) for r in p.rows] == [("A", 12), ("B", None)]
    assert [(e.row, e.column) for e in p.errors] == [(4, "quantity"), (5, "quantity"), (6, "quantity")]


def test_stock_format_needs_a_quantity_on_every_row_and_any_column_order() -> None:
    p = parsed("quantity,product_name\n5,Fridge\n,Washer\n")
    assert p.format is ImportFormat.STOCK
    assert [(r.name, r.quantity, r.regular_price) for r in p.rows] == [("Fridge", 5, None)]
    assert [(e.row, e.column) for e in p.errors] == [(3, "quantity")]


def test_row_and_size_limits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(csv_import, "MAX_ROWS", 2)
    result = parse_csv_text(f"{HEADER}\nA,1,1\nB,1,1\nC,1,1\n")
    assert isinstance(result, Err) and "Too many rows" in result.error

    path = tmp_path / "big.csv"
    path.write_text(f"{HEADER}\nA,1,1\n", encoding="utf-8")
    monkeypatch.setattr(csv_import, "MAX_FILE_BYTES", 5)
    assert isinstance(parse_csv_file(path), Err)


def test_non_utf8_file_gets_a_helpful_error(tmp_path: Path) -> None:
    path = tmp_path / "turkish.csv"
    path.write_bytes(f"{HEADER}\nÇamaşır,1,2\n".encode("cp1254"))
    result = parse_csv_file(path)
    assert isinstance(result, Err) and "UTF-8" in result.error


# ---- planning -------------------------------------------------------------


def test_plan_classifies_every_row(repo) -> None:  # type: ignore[no-untyped-def]
    add(repo, "Fridge")
    add(repo, "Washer", "6000", "5000")
    add(repo, "Freezer", "3000", "2500")
    dryer = add(repo, "Dryer", "2000", "1500")
    repo.archive(dryer.id)
    plan = plan_for(
        f"{HEADER_Q}\nFridge,5000,4000,\nWasher,6000,5000,3\nFreezer,3500,2500,\n"
        "Dryer,2000,1500,\nOven,100,90,1\n",
        repo,
    )
    assert kinds(plan) == {
        "Fridge": Kind.UNCHANGED,
        "Washer": Kind.STOCK_UPDATE,
        "Freezer": Kind.CONFLICT,
        "Dryer": Kind.CONFLICT,
        "Oven": Kind.NEW,
    }
    assert [i.restores for i in plan.items if i.row.name == "Dryer"] == [True]


def test_stock_plan_never_creates_and_rejects_unknown_or_archived(repo) -> None:  # type: ignore[no-untyped-def]
    fridge = add(repo, "Fridge")
    old = add(repo, "Old")
    repo.archive(old.id)
    plan = plan_for("product_name,quantity\nFridge,5\nGhost,1\nOld,2\n", repo)
    assert kinds(plan) == {"Fridge": Kind.STOCK_UPDATE}
    assert [(e.row, e.column) for e in plan.errors] == [(3, "product_name"), (4, "product_name")]

    repo.set_quantity(fridge.id, 5, csv_import.StockSource.MANUAL)
    plan = plan_for("product_name,quantity\nFridge,5\n", repo)
    assert kinds(plan) == {"Fridge": Kind.UNCHANGED}


# ---- applying -------------------------------------------------------------


def test_apply_creates_updates_and_skips_per_decision(repo, db, clock) -> None:  # type: ignore[no-untyped-def]
    fridge = add(repo, "Fridge", gift="Vacuum", notes="check")
    washer = add(repo, "Washer", "6000", "5000")
    plan = plan_for(
        f"{HEADER_Q}\nFridge,5.500,00,4500,7\nWasher,7000,6000,\nOven,100,90,4\n".replace(
            "5.500,00", '"5.500,00"'
        ),
        repo,
    )
    fridge_row, washer_row = (i.row.row for i in plan.conflicts)
    result = apply_plan(
        db,
        plan,
        {fridge_row: Decision.UPDATE, washer_row: Decision.SKIP},
        note="csv: in.csv",
        clock=clock,
    )
    assert isinstance(result, Ok)
    s = result.value
    assert (s.created, s.updated, s.skipped, s.stock_updated) == (1, 1, 1, 2)

    f = repo.get(fridge.id)
    assert f is not None and (f.regular_price, f.website_price, f.quantity) == (D("5500"), D("4500"), 7)
    assert (f.default_gift_name, f.notes, f.name) == ("Vacuum", "check", "Fridge")
    assert repo.get(washer.id) == washer  # skipped: nothing changed
    [oven] = repo.search("oven")
    assert oven.quantity == 4
    history = db.execute(
        "SELECT regular_price FROM pricing_history WHERE product_id = ? ORDER BY id", (fridge.id,)
    ).fetchall()
    assert [D(r[0]) for r in history] == [D("5000"), D("5500")]
    note = db.execute("SELECT DISTINCT note FROM stock_history").fetchone()[0]
    assert note == "csv: in.csv"
    assert not db.in_transaction


def test_every_conflict_needs_a_decision(repo, db) -> None:  # type: ignore[no-untyped-def]
    add(repo, "Fridge")
    plan = plan_for(f"{HEADER}\nFridge,6000,4000\nOven,1,1\n", repo)
    result = apply_plan(db, plan, {})
    assert isinstance(result, Err) and result.error.code == "undecided"
    assert [p.name for p in repo.search()] == ["Fridge"]  # nothing applied


def test_errors_block_the_import_unless_valid_only(repo, db) -> None:  # type: ignore[no-untyped-def]
    plan = plan_for(f"{HEADER}\nOven,100,90\nBad,abc,1\n", repo)
    blocked = apply_plan(db, plan, {})
    assert isinstance(blocked, Err) and blocked.error.code == "has_errors"
    assert repo.search() == []

    result = apply_plan(db, plan, {}, import_valid_only=True)
    assert isinstance(result, Ok)
    assert (result.value.created, result.value.rows_with_errors) == (1, 1)


def test_archived_match_is_updated_and_restored(repo, db) -> None:  # type: ignore[no-untyped-def]
    dryer = add(repo, "Dryer", "2000", "1500", gift="Hose")
    repo.archive(dryer.id)
    plan = plan_for(f"{HEADER}\nDryer,2500,1800\n", repo)
    result = apply_plan(db, plan, update_all(plan))
    assert isinstance(result, Ok) and (result.value.updated, result.value.restored) == (1, 1)
    restored = repo.get(dryer.id)
    assert restored is not None and not restored.archived
    assert (restored.website_price, restored.default_gift_name) == (D("1800"), "Hose")


def test_a_failure_in_the_middle_rolls_everything_back(repo, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fridge = add(repo, "Fridge")
    plan = plan_for(f"{HEADER}\nFridge,6000,4000\nA,1,1\nB,2,2\n", repo)
    original = ProductRepository.add
    calls = {"n": 0}

    def flaky(self, draft):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 2:
            raise sqlite3.OperationalError("boom")
        return original(self, draft)

    monkeypatch.setattr(ProductRepository, "add", flaky)
    result = apply_plan(db, plan, update_all(plan))
    assert isinstance(result, Err) and result.error.code == "failed"
    assert repo.get(fridge.id) == fridge
    assert [p.name for p in repo.search()] == ["Fridge"]
    assert not db.in_transaction


def test_a_stale_plan_rolls_back_instead_of_half_applying(repo, db) -> None:  # type: ignore[no-untyped-def]
    fridge = add(repo, "Fridge")
    plan = plan_for(f"{HEADER}\nFridge,6000,4000\nOven,1,1\n", repo)
    add(repo, "Oven")  # appears after the preview was made
    result = apply_plan(db, plan, update_all(plan))
    assert isinstance(result, Err) and result.error.code == "rolled_back"
    assert "Oven" in result.error.message
    assert repo.get(fridge.id) == fridge


def test_stock_only_import_updates_counts_without_touching_prices(repo, db) -> None:  # type: ignore[no-untyped-def]
    fridge = add(repo, "Fridge")
    washer = add(repo, "Washer")
    repo.set_quantity(washer.id, 4, csv_import.StockSource.MANUAL)
    plan = plan_for("product_name,quantity\nFridge,5\nWasher,4\n", repo)
    result = apply_plan(db, plan, {})
    assert isinstance(result, Ok)
    assert (result.value.stock_updated, result.value.unchanged) == (1, 1)
    updated = repo.get(fridge.id)
    assert updated is not None and updated.quantity == 5
    assert (updated.regular_price, updated.updated_at) == (fridge.regular_price, fridge.updated_at)