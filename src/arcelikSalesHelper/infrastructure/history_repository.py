from __future__ import annotations

import sqlite3

from arcelikSalesHelper.application.history import (
    LineRecord,
    SnapshotHeader,
    SnapshotRecord,
)

from .database import transaction

_SNAPSHOT_COLS = "id, created_at, app_version, schema_version, totals_json, confirmation_state, warnings_json"
_LINE_COLS = (
    "line_index, product_id, product_name, quantity, regular_price, website_price, coupon, "
    "effective_website_unit, gift_selected, gift_name, manager_value_entered, manager_mode, "
    "manager_line_total, manager_unit, result_json, entered_json"
)


def _to_line(row: sqlite3.Row) -> LineRecord:
    return LineRecord(
        line_index=int(row["line_index"]),
        product_id=row["product_id"],
        product_name=row["product_name"],
        quantity=int(row["quantity"]),
        regular_price=row["regular_price"],
        website_price=row["website_price"],
        coupon=row["coupon"],
        effective_website_unit=row["effective_website_unit"],
        gift_selected=bool(row["gift_selected"]),
        gift_name=row["gift_name"],
        manager_value_entered=row["manager_value_entered"],
        manager_mode=row["manager_mode"],
        manager_line_total=row["manager_line_total"],
        manager_unit=row["manager_unit"],
        result_json=row["result_json"],
        entered_json=row["entered_json"],
    )


class HistoryRepository:
    """Append-only. There is deliberately no update or delete method."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, record: SnapshotRecord) -> int:
        """Write the snapshot and all its lines in one transaction; return the new id.

        Raises sqlite3.Error after rolling back if anything fails.
        """
        with transaction(self._conn):
            cur = self._conn.execute(
                "INSERT INTO calculation_snapshots (created_at, app_version, schema_version, "
                "totals_json, confirmation_state, warnings_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.created_at,
                    record.app_version,
                    record.schema_version,
                    record.totals_json,
                    record.confirmation_state,
                    record.warnings_json,
                ),
            )
            snapshot_id = cur.lastrowid
            if snapshot_id is None:
                raise RuntimeError("INSERT returned no rowid")
            for line in record.lines:
                self._conn.execute(
                    f"INSERT INTO calculation_lines (snapshot_id, {_LINE_COLS}) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        snapshot_id,
                        line.line_index,
                        line.product_id,
                        line.product_name,
                        line.quantity,
                        line.regular_price,
                        line.website_price,
                        line.coupon,
                        line.effective_website_unit,
                        1 if line.gift_selected else 0,
                        line.gift_name,
                        line.manager_value_entered,
                        line.manager_mode,
                        line.manager_line_total,
                        line.manager_unit,
                        line.result_json,
                        line.entered_json,
                    ),
                )
        return snapshot_id

    def get(self, snapshot_id: int) -> SnapshotRecord | None:
        row = self._conn.execute(
            f"SELECT {_SNAPSHOT_COLS} FROM calculation_snapshots WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            return None
        lines = self._conn.execute(
            f"SELECT {_LINE_COLS} FROM calculation_lines WHERE snapshot_id = ? "
            "ORDER BY line_index",
            (snapshot_id,),
        )
        return SnapshotRecord(
            id=int(row["id"]),
            created_at=row["created_at"],
            app_version=row["app_version"],
            schema_version=int(row["schema_version"]),
            totals_json=row["totals_json"],
            confirmation_state=row["confirmation_state"] or "",
            warnings_json=row["warnings_json"],
            lines=tuple(_to_line(r) for r in lines),
        )

    def count(self) -> int:
        return int(
            self._conn.execute(
                "SELECT COUNT(*) FROM calculation_snapshots"
            ).fetchone()[0]
        )

    def list_headers(
        self, limit: int = 100, before_id: int | None = None
    ) -> list[SnapshotHeader]:
        """Newest first. ``before_id`` pages backwards and stays stable while new ones arrive."""
        sql = (
            "SELECT s.id, s.created_at, s.totals_json, "
            "(SELECT COUNT(*) FROM calculation_lines l WHERE l.snapshot_id = s.id) AS line_count "
            "FROM calculation_snapshots s"
        )
        params: list[object] = []
        if before_id is not None:
            sql += " WHERE s.id < ?"
            params.append(before_id)
        sql += " ORDER BY s.id DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        if not rows:
            return []
        ids = [int(r["id"]) for r in rows]
        names: dict[int, list[str]] = {i: [] for i in ids}
        marks = ",".join("?" * len(ids))
        for r in self._conn.execute(
            "SELECT snapshot_id, product_name FROM calculation_lines "
            f"WHERE snapshot_id IN ({marks}) ORDER BY snapshot_id, line_index",
            ids,
        ):
            names[int(r["snapshot_id"])].append(r["product_name"])
        return [
            SnapshotHeader(
                id=int(r["id"]),
                created_at=r["created_at"],
                line_count=int(r["line_count"]),
                product_names=tuple(names[int(r["id"])]),
                totals_json=r["totals_json"],
            )
            for r in rows
        ]
