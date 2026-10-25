"""CSV import. Parsing and planning are pure; only ``apply_plan`` touches the database.

Two formats, detected from the header:
  prices: product_name,regular_price,website_discounted_price[,quantity]
  stock : product_name,quantity           (never creates products)
"""

from __future__ import annotations

import csv
import io
import logging
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

from arcelikSalesHelper.domain.formatting import format_try
from arcelikSalesHelper.domain.money import parse_money_ex
from arcelikSalesHelper.domain.products import (
    MAX_NAME_LENGTH,
    Product,
    ProductDraft,
    name_key,
)
from arcelikSalesHelper.domain.result import Err, Ok, Result
from arcelikSalesHelper.domain.stock import StockSource, parse_quantity

from .database import transaction
from .repositories import ProductRepository, RepoError, utc_now

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = (
    "product_name",
    "regular_price",
    "website_discounted_price",
)
QUANTITY_COLUMN = "quantity"
STOCK_ONLY_COLUMNS = ("product_name", QUANTITY_COLUMN)
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_ROWS = 100_000

_EXPECTED = (
    "Expected product_name,regular_price,website_discounted_price (optionally followed by "
    "quantity), or product_name,quantity for stock counts."
)


class ImportFormat(Enum):
    PRICES = "prices"
    STOCK = "stock"


class Kind(Enum):
    NEW = "new"
    CONFLICT = (
        "conflict"  # prices differ, or the match is archived: needs a decision
    )
    STOCK_UPDATE = (
        "stock_update"  # only the counted quantity changes: no decision needed
    )
    UNCHANGED = "unchanged"


class Decision(Enum):
    UPDATE = "update"  # for an archived match this also restores it
    SKIP = "skip"


@dataclass(frozen=True)
class RowError:
    row: int  # 1-based, the header is row 1
    column: str | None
    message: str


@dataclass(frozen=True)
class ParsedRow:
    row: int
    name: str
    key: str
    regular_price: Decimal | None  # None in the stock format
    website_price: Decimal | None
    quantity: int | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedCsv:
    format: ImportFormat
    rows: tuple[ParsedRow, ...]
    errors: tuple[RowError, ...]
    blank_rows: int = 0


@dataclass(frozen=True)
class PlanItem:
    row: ParsedRow
    kind: Kind
    existing: Product | None = None

    @property
    def restores(self) -> bool:
        return self.existing is not None and self.existing.archived


@dataclass(frozen=True)
class ImportPlan:
    format: ImportFormat
    items: tuple[PlanItem, ...]
    errors: tuple[RowError, ...]

    @property
    def conflicts(self) -> tuple[PlanItem, ...]:
        return tuple(i for i in self.items if i.kind is Kind.CONFLICT)

    @property
    def actionable(self) -> bool:
        return any(i.kind is not Kind.UNCHANGED for i in self.items)


@dataclass(frozen=True)
class ImportSummary:
    created: int
    updated: int
    restored: int
    stock_updated: int
    skipped: int
    unchanged: int
    rows_with_errors: int

    def lines(self) -> tuple[str, ...]:
        out = [
            f"New products: {self.created}",
            f"Prices updated: {self.updated}",
            f"Restored from archive: {self.restored}",
            f"Quantities updated: {self.stock_updated}",
            f"Skipped by you: {self.skipped}",
            f"Unchanged: {self.unchanged}",
        ]
        if self.rows_with_errors:
            out.append(f"Rows with errors, left out: {self.rows_with_errors}")
        return tuple(out)


@dataclass(frozen=True)
class ImportFailure:
    code: str  # has_errors | undecided | rolled_back | failed
    message: str


# --------------------------------------------------------------------------
# parsing (pure)
# --------------------------------------------------------------------------


def _detect_format(header: Sequence[str]) -> Result[ImportFormat, str]:
    if len(header) == 1 and (";" in header[0] or "\t" in header[0]):
        return Err(
            "The file looks semicolon- or tab-delimited. Save it as comma-delimited CSV "
            'and quote prices that contain a comma, for example "54.999,00".'
        )
    if len(set(header)) != len(header):
        return Err(
            "Invalid header: a column name appears more than once. "
            + _EXPECTED
        )
    present = set(header)
    if present == set(STOCK_ONLY_COLUMNS):
        return Ok(ImportFormat.STOCK)
    missing = [c for c in REQUIRED_COLUMNS if c not in present]
    unknown = sorted(present - set(REQUIRED_COLUMNS) - {QUANTITY_COLUMN})
    problems: list[str] = []
    if missing:
        problems.append("missing column(s): " + ", ".join(missing))
    if unknown:
        problems.append("unexpected column(s): " + ", ".join(unknown))
    if problems:
        return Err("Invalid header: " + "; ".join(problems) + ". " + _EXPECTED)
    return Ok(ImportFormat.PRICES)


def _price(
    line: int,
    column: str,
    text: str,
    errors: list[RowError],
    warnings: list[str],
) -> Decimal | None:
    match parse_money_ex(text):
        case Ok(parsed):
            if parsed.ambiguous:
                warnings.append(
                    f"{column}: '{text}' was read as {format_try(parsed.value)} "
                    "(dot as thousands separator)"
                )
            return parsed.value
        case Err(message):
            errors.append(RowError(line, column, message))
    return None


def _parse_row(
    line: int,
    cells: Sequence[str],
    index: Mapping[str, int],
    fmt: ImportFormat,
    seen: dict[str, int],
) -> tuple[list[RowError], ParsedRow | None]:
    def get(column: str) -> str:
        i = index.get(column)
        return "" if i is None or i >= len(cells) else cells[i].strip()

    errors: list[RowError] = []
    warnings: list[str] = []

    name = " ".join(get("product_name").split())
    key = name_key(name) if name else ""
    if not name:
        errors.append(
            RowError(line, "product_name", "Product name is required.")
        )
    elif len(name) > MAX_NAME_LENGTH:
        errors.append(
            RowError(
                line,
                "product_name",
                f"Name must be at most {MAX_NAME_LENGTH} characters.",
            )
        )
    elif key in seen:
        errors.append(
            RowError(
                line,
                "product_name",
                f"Duplicate of row {seen[key]} (same product name).",
            )
        )
    else:
        seen[key] = line

    regular: Decimal | None = None
    website: Decimal | None = None
    if fmt is ImportFormat.PRICES:
        regular = _price(
            line, "regular_price", get("regular_price"), errors, warnings
        )
        website = _price(
            line,
            "website_discounted_price",
            get("website_discounted_price"),
            errors,
            warnings,
        )

    quantity: int | None = None
    qty_text = get(QUANTITY_COLUMN)
    if qty_text or fmt is ImportFormat.STOCK:
        match parse_quantity(qty_text):
            case Ok(value):
                quantity = value
            case Err(message):
                errors.append(RowError(line, QUANTITY_COLUMN, message))

    if errors:
        return errors, None
    return errors, ParsedRow(
        line, name, key, regular, website, quantity, tuple(warnings)
    )


def parse_csv_text(text: str) -> Result[ParsedCsv, str]:
    text = text.removeprefix("\ufeff")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=",")
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        return Err("The file is empty.")
    except csv.Error as exc:
        return Err(f"The file is not valid CSV: {exc}")

    detected = _detect_format(header)
    if isinstance(detected, Err):
        return Err(detected.error)
    fmt = detected.value
    index = {name: i for i, name in enumerate(header)}

    rows: list[ParsedRow] = []
    errors: list[RowError] = []
    seen: dict[str, int] = {}
    blank = 0
    count = 0
    try:
        for cells in reader:
            line = reader.line_num
            if not any(c.strip() for c in cells):
                blank += 1
                continue
            count += 1
            if count > MAX_ROWS:
                return Err(f"Too many rows (the limit is {MAX_ROWS:,}).")
            if len(cells) > len(header) and any(
                c.strip() for c in cells[len(header) :]
            ):
                errors.append(
                    RowError(
                        line,
                        None,
                        "Row has more cells than the header. Quote values that contain a comma.",
                    )
                )
                continue
            row_errors, row = _parse_row(line, cells, index, fmt, seen)
            errors.extend(row_errors)
            if row is not None:
                rows.append(row)
    except csv.Error as exc:
        return Err(
            f"The file is not valid CSV near line {reader.line_num}: {exc}"
        )
    return Ok(ParsedCsv(fmt, tuple(rows), tuple(errors), blank))


def parse_csv_file(path: Path) -> Result[ParsedCsv, str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return Err(
                f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB."
            )
        text = path.read_bytes().decode("utf-8-sig")
    except OSError as exc:
        return Err(f"Cannot read the file: {exc}")
    except UnicodeDecodeError:
        return Err("The file is not valid UTF-8. Save it as 'CSV UTF-8'.")
    return parse_csv_text(text)


# --------------------------------------------------------------------------
# planning (pure)
# --------------------------------------------------------------------------


def index_products(products: Iterable[Product]) -> dict[str, Product]:
    """name_key -> product. An active product wins over archived ones, then the newest."""
    chosen: dict[str, Product] = {}
    for p in products:
        key = name_key(p.name)
        cur = chosen.get(key)
        if (
            cur is None
            or (cur.archived and not p.archived)
            or (cur.archived == p.archived and p.id > cur.id)
        ):
            chosen[key] = p
    return chosen


def plan_import(
    parsed: ParsedCsv, existing_by_key: Mapping[str, Product]
) -> ImportPlan:
    items: list[PlanItem] = []
    errors = list(parsed.errors)
    for row in parsed.rows:
        existing = existing_by_key.get(row.key)
        if parsed.format is ImportFormat.STOCK:
            if existing is None:
                errors.append(
                    RowError(
                        row.row,
                        "product_name",
                        "No product with this name. Add it first; stock files never "
                        "create products.",
                    )
                )
            elif existing.archived:
                errors.append(
                    RowError(
                        row.row,
                        "product_name",
                        "This product is archived. Restore it before updating its quantity.",
                    )
                )
            elif row.quantity == existing.quantity:
                items.append(PlanItem(row, Kind.UNCHANGED, existing))
            else:
                items.append(PlanItem(row, Kind.STOCK_UPDATE, existing))
            continue

        if existing is None:
            items.append(PlanItem(row, Kind.NEW))
        elif (
            existing.archived
            or existing.regular_price != row.regular_price
            or existing.website_price != row.website_price
        ):
            items.append(PlanItem(row, Kind.CONFLICT, existing))
        elif row.quantity is not None and row.quantity != existing.quantity:
            items.append(PlanItem(row, Kind.STOCK_UPDATE, existing))
        else:
            items.append(PlanItem(row, Kind.UNCHANGED, existing))
    errors.sort(key=lambda e: e.row)
    return ImportPlan(parsed.format, tuple(items), tuple(errors))


# --------------------------------------------------------------------------
# applying (one transaction)
# --------------------------------------------------------------------------


class _Abort(Exception):
    pass


@dataclass
class _Counts:
    created: int = 0
    updated: int = 0
    restored: int = 0
    stock_updated: int = 0
    skipped: int = 0
    unchanged: int = 0


def _ok(result: Result[Product, RepoError], row: ParsedRow) -> Product:
    if isinstance(result, Err):
        raise _Abort(f"Row {row.row} ({row.name}): {result.error.message}")
    return result.value


def _prices(row: ParsedRow) -> tuple[Decimal, Decimal]:
    if row.regular_price is None or row.website_price is None:
        raise _Abort(f"Row {row.row} ({row.name}): prices are missing.")
    return row.regular_price, row.website_price


def apply_plan(
    conn: sqlite3.Connection,
    plan: ImportPlan,
    decisions: Mapping[int, Decision],
    *,
    import_valid_only: bool = False,
    note: str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> Result[ImportSummary, ImportFailure]:
    """Apply the plan atomically. Any failure rolls back the whole import.

    Existing products keep their name, default gift and notes: only prices,
    archived state and the counted quantity can change.
    """
    if plan.errors and not import_valid_only:
        return Err(
            ImportFailure(
                "has_errors",
                f"The file has {len(plan.errors)} row error(s). Fix the file, or choose to "
                "import the valid rows only.",
            )
        )
    undecided = [
        i.row.row for i in plan.conflicts if i.row.row not in decisions
    ]
    if undecided:
        shown = ", ".join(str(r) for r in undecided[:10]) + (
            " ..." if len(undecided) > 10 else ""
        )
        return Err(
            ImportFailure(
                "undecided",
                f"Choose Update or Skip for every conflict (rows {shown}).",
            )
        )

    repo = ProductRepository(conn, clock)
    counts = _Counts()

    def set_stock(product_id: int, row: ParsedRow) -> None:
        if row.quantity is None:
            return
        _ok(
            repo.set_quantity(product_id, row.quantity, StockSource.CSV, note),
            row,
        )
        counts.stock_updated += 1

    try:
        with transaction(conn):
            for item in plan.items:
                row, existing = item.row, item.existing
                match item.kind:
                    case Kind.UNCHANGED:
                        counts.unchanged += 1
                    case Kind.NEW:
                        regular, website = _prices(row)
                        created = _ok(
                            repo.add(ProductDraft(row.name, regular, website)),
                            row,
                        )
                        counts.created += 1
                        set_stock(created.id, row)
                    case Kind.STOCK_UPDATE:
                        if existing is None:
                            raise _Abort(
                                f"Row {row.row}: product missing from the plan."
                            )
                        set_stock(existing.id, row)
                    case Kind.CONFLICT:
                        if existing is None:
                            raise _Abort(
                                f"Row {row.row}: product missing from the plan."
                            )
                        if decisions[row.row] is Decision.SKIP:
                            counts.skipped += 1
                            continue
                        regular, website = _prices(row)
                        draft = ProductDraft(
                            existing.name,
                            regular,
                            website,
                            existing.default_gift_name,
                            existing.notes,
                        )
                        _ok(repo.update(existing.id, draft), row)
                        if (
                            existing.regular_price != regular
                            or existing.website_price != website
                        ):
                            counts.updated += 1
                        if existing.archived:
                            _ok(repo.restore(existing.id), row)
                            counts.restored += 1
                        if (
                            row.quantity is not None
                            and row.quantity != existing.quantity
                        ):
                            set_stock(existing.id, row)
    except _Abort as exc:
        return Err(
            ImportFailure("rolled_back", f"Nothing was imported. {exc}")
        )
    except sqlite3.Error as exc:
        log.exception("CSV import failed")
        return Err(
            ImportFailure(
                "failed", f"Nothing was imported. Database error: {exc}"
            )
        )

    return Ok(
        ImportSummary(
            counts.created,
            counts.updated,
            counts.restored,
            counts.stock_updated,
            counts.skipped,
            counts.unchanged,
            len(plan.errors),
        )
    )
