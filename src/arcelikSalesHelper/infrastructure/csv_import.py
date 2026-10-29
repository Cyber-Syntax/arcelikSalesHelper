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

from arcelikSalesHelper import strings as T
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
)
WEBSITE_PRICE_COLUMN = "website_discounted_price"
QUANTITY_COLUMN = "quantity"
_FORMULA_PREFIXES = "=+-@\t\r"
STOCK_ONLY_COLUMNS = ("product_name", QUANTITY_COLUMN)
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_ROWS = 100_000


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
        return T.import_summary_lines(
            self.created,
            self.updated,
            self.restored,
            self.stock_updated,
            self.skipped,
            self.unchanged,
            self.rows_with_errors,
        )


@dataclass(frozen=True)
class ImportFailure:
    code: str  # has_errors | undecided | rolled_back | failed
    message: str


# --------------------------------------------------------------------------
# parsing (pure)
# --------------------------------------------------------------------------


def _detect_format(header: Sequence[str]) -> Result[ImportFormat, str]:
    if len(header) == 1 and (";" in header[0] or "\t" in header[0]):
        return Err(T.CSV_DELIMITER)
    if len(set(header)) != len(header):
        return Err(T.csv_duplicate_header())
    present = set(header)
    if present == set(STOCK_ONLY_COLUMNS):
        return Ok(ImportFormat.STOCK)
    missing = [c for c in REQUIRED_COLUMNS if c not in present]
    unknown = sorted(
        present
        - set(REQUIRED_COLUMNS)
        - {WEBSITE_PRICE_COLUMN, QUANTITY_COLUMN}
    )
    if missing or unknown:
        return Err(T.csv_bad_header(missing, unknown))
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
                    T.csv_ambiguous(column, text, format_try(parsed.value))
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

    name = _restore_exported_name(" ".join(get("product_name").split()))
    key = name_key(name) if name else ""
    if not name:
        errors.append(RowError(line, "product_name", T.VAL_NAME_REQUIRED))
    elif len(name) > MAX_NAME_LENGTH:
        errors.append(
            RowError(
                line,
                "product_name",
                T.val_name_too_long(MAX_NAME_LENGTH),
            )
        )
    elif key in seen:
        errors.append(
            RowError(
                line,
                "product_name",
                T.csv_duplicate_row(seen[key]),
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
        website_text = get(WEBSITE_PRICE_COLUMN)
        website = (
            _price(line, WEBSITE_PRICE_COLUMN, website_text, errors, warnings)
            if website_text
            else Decimal(0)
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


def _restore_exported_name(name: str) -> str:
    """Undo the exporter’s formula escape, including escaped literal apostrophes."""
    if not name.startswith("'"):
        return name
    value = name[1:]
    marker = len(value) - len(value.lstrip())
    if value[marker : marker + 1] in _FORMULA_PREFIXES:
        return value
    if value.startswith("'"):
        literal = value[1:]
        marker = len(literal) - len(literal.lstrip())
        if literal[marker : marker + 1] in _FORMULA_PREFIXES:
            return literal
    return name


def parse_csv_text(text: str) -> Result[ParsedCsv, str]:
    text = text.removeprefix("\ufeff")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=",")
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        return Err(T.CSV_EMPTY)
    except csv.Error as exc:
        return Err(T.csv_not_valid(str(exc)))

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
                return Err(T.csv_too_many_rows(MAX_ROWS))
            if len(cells) > len(header) and any(
                c.strip() for c in cells[len(header) :]
            ):
                errors.append(
                    RowError(
                        line,
                        None,
                        T.CSV_EXTRA_CELLS,
                    )
                )
                continue
            row_errors, row = _parse_row(line, cells, index, fmt, seen)
            errors.extend(row_errors)
            if row is not None:
                rows.append(row)
    except csv.Error as exc:
        return Err(T.csv_not_valid_near(reader.line_num, str(exc)))
    return Ok(ParsedCsv(fmt, tuple(rows), tuple(errors), blank))


def parse_csv_file(path: Path) -> Result[ParsedCsv, str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return Err(T.csv_too_large(MAX_FILE_BYTES // (1024 * 1024)))
        text = path.read_bytes().decode("utf-8-sig")
    except OSError as exc:
        return Err(T.csv_cannot_read(str(exc)))
    except UnicodeDecodeError:
        return Err(T.CSV_NOT_UTF8)
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
                        T.CSV_NO_SUCH_PRODUCT,
                    )
                )
            elif existing.archived:
                errors.append(
                    RowError(
                        row.row,
                        "product_name",
                        T.CSV_ARCHIVED_STOCK,
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
        raise _Abort(
            T.import_row_problem(row.row, row.name, result.error.message)
        )
    return result.value


def _prices(row: ParsedRow) -> tuple[Decimal, Decimal]:
    if row.regular_price is None or row.website_price is None:
        raise _Abort(T.import_prices_missing(row.row, row.name))
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
                T.import_has_errors(len(plan.errors)),
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
                T.import_undecided(shown),
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
                            raise _Abort(T.import_row_no_plan(row.row))
                        set_stock(existing.id, row)
                    case Kind.CONFLICT:
                        if existing is None:
                            raise _Abort(T.import_row_no_plan(row.row))
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
            ImportFailure("rolled_back", T.import_rolled_back(str(exc)))
        )
    except sqlite3.Error as exc:
        log.exception("CSV import failed")
        return Err(ImportFailure("failed", T.import_db_error(str(exc))))

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
