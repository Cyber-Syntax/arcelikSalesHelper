from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from arcelikSalesHelper.domain.formatting import format_decimal_exact
from arcelikSalesHelper.domain.products import (
    Product,
    ProductDraft,
    name_key,
    normalize_draft,
    validate_draft,
)
from arcelikSalesHelper.domain.result import Err, Ok, Result
from arcelikSalesHelper.domain.validation import ValidationError

from .database import transaction

_COLUMNS = (
    "id, name, regular_price, website_price, default_gift_name, notes, "
    "archived, created_at, updated_at"
)


@dataclass(frozen=True)
class RepoError:
    code: str  # invalid | not_found | duplicate_name | name_collision
    message: str
    details: tuple[ValidationError, ...] = ()


def utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_product(row: sqlite3.Row) -> Product:
    return Product(
        id=int(row["id"]),
        name=row["name"],
        regular_price=Decimal(row["regular_price"]),
        website_price=Decimal(row["website_price"]),
        default_gift_name=row["default_gift_name"],
        notes=row["notes"],
        archived=bool(row["archived"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _duplicate(name: str) -> RepoError:
    return RepoError(
        "duplicate_name", f"An active product named '{name}' already exists."
    )


def _not_found(product_id: int) -> RepoError:
    return RepoError("not_found", f"Product {product_id} does not exist.")


class ProductRepository:
    def __init__(
        self, conn: sqlite3.Connection, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._conn = conn
        self._clock = clock

    # ---- reads -----------------------------------------------------------

    def get(self, product_id: int) -> Product | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        return None if row is None else _to_product(row)

    def search(
        self, query: str = "", include_archived: bool = False
    ) -> list[Product]:
        pattern = f"%{_escape_like(name_key(query))}%"
        sql = f"SELECT {_COLUMNS} FROM products WHERE name_key LIKE ? ESCAPE '\\'"
        if not include_archived:
            sql += " AND archived = 0"
        sql += " ORDER BY name_key, id"
        return [_to_product(r) for r in self._conn.execute(sql, (pattern,))]

    # ---- writes ----------------------------------------------------------

    def add(self, draft: ProductDraft) -> Result[Product, RepoError]:
        d = normalize_draft(draft)
        errors = validate_draft(d)
        if errors:
            return Err(RepoError("invalid", errors[0].message, errors))
        key = name_key(d.name)
        with transaction(self._conn):
            if self._active_id(key) is not None:
                return Err(_duplicate(d.name))
            now = _iso(self._clock())
            cur = self._conn.execute(
                "INSERT INTO products (name, name_key, regular_price, website_price, "
                "default_gift_name, notes, archived, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (
                    d.name,
                    key,
                    format_decimal_exact(d.regular_price),
                    format_decimal_exact(d.website_price),
                    d.default_gift_name,
                    d.notes,
                    now,
                    now,
                ),
            )
            product_id = cur.lastrowid
            if product_id is None:
                raise RuntimeError("INSERT returned no rowid")
            self._record_prices(
                product_id, d.regular_price, d.website_price, now
            )
            return Ok(self._require(product_id))

    def update(
        self, product_id: int, draft: ProductDraft
    ) -> Result[Product, RepoError]:
        d = normalize_draft(draft)
        errors = validate_draft(d)
        if errors:
            return Err(RepoError("invalid", errors[0].message, errors))
        key = name_key(d.name)
        with transaction(self._conn):
            current = self.get(product_id)
            if current is None:
                return Err(_not_found(product_id))
            if not current.archived:
                other = self._active_id(key)
                if other is not None and other != product_id:
                    return Err(_duplicate(d.name))
            prices_changed = (
                current.regular_price != d.regular_price
                or current.website_price != d.website_price
            )
            unchanged = (
                not prices_changed
                and current.name == d.name
                and current.default_gift_name == d.default_gift_name
                and current.notes == d.notes
            )
            if unchanged:
                return Ok(current)  # no write, no timestamp bump
            now = _iso(self._clock())
            self._conn.execute(
                "UPDATE products SET name = ?, name_key = ?, regular_price = ?, "
                "website_price = ?, default_gift_name = ?, notes = ?, updated_at = ? "
                "WHERE id = ?",
                (
                    d.name,
                    key,
                    format_decimal_exact(d.regular_price),
                    format_decimal_exact(d.website_price),
                    d.default_gift_name,
                    d.notes,
                    now,
                    product_id,
                ),
            )
            if prices_changed:
                self._record_prices(
                    product_id, d.regular_price, d.website_price, now
                )
            return Ok(self._require(product_id))

    def archive(self, product_id: int) -> Result[Product, RepoError]:
        return self._set_archived(product_id, archived=True)

    def restore(self, product_id: int) -> Result[Product, RepoError]:
        return self._set_archived(product_id, archived=False)

    # ---- internals -------------------------------------------------------

    def _set_archived(
        self, product_id: int, archived: bool
    ) -> Result[Product, RepoError]:
        with transaction(self._conn):
            current = self.get(product_id)
            if current is None:
                return Err(_not_found(product_id))
            if current.archived == archived:
                return Ok(current)  # idempotent
            if not archived:
                other = self._active_id(name_key(current.name))
                if other is not None:
                    return Err(
                        RepoError(
                            "name_collision",
                            f"Cannot restore: an active product named '{current.name}' "
                            "already exists. Rename or archive one of them first.",
                        )
                    )
            self._conn.execute(
                "UPDATE products SET archived = ?, updated_at = ? WHERE id = ?",
                (1 if archived else 0, _iso(self._clock()), product_id),
            )
            return Ok(self._require(product_id))

    def _active_id(self, key: str) -> int | None:
        row = self._conn.execute(
            "SELECT id FROM products WHERE name_key = ? AND archived = 0",
            (key,),
        ).fetchone()
        return None if row is None else int(row["id"])

    def _record_prices(
        self,
        product_id: int,
        regular: Decimal,
        website: Decimal,
        changed_at: str,
    ) -> None:
        self._conn.execute(
            "INSERT INTO pricing_history (product_id, regular_price, website_price, changed_at) "
            "VALUES (?, ?, ?, ?)",
            (
                product_id,
                format_decimal_exact(regular),
                format_decimal_exact(website),
                changed_at,
            ),
        )

    def _require(self, product_id: int) -> Product:
        product = self.get(product_id)
        if product is None:
            raise RuntimeError(
                f"product {product_id} vanished inside a transaction"
            )
        return product
