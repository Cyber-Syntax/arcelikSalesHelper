"""Change report: what the apply did, row by row."""

from __future__ import annotations

import csv
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.domain.formatting import format_decimal_exact

from .csv_export import _safe_text_cell
from .csv_import import Decision, ImportPlan, Kind


@dataclass(frozen=True)
class ReportRow:
    name: str
    status: str
    old_regular: Decimal | None
    new_regular: Decimal | None
    old_website: Decimal | None
    new_website: Decimal | None


def build_report_rows(
    plan: ImportPlan,
    decisions: Mapping[int, Decision],
    skipped_new: Collection[int] = frozenset(),
) -> tuple[ReportRow, ...]:
    """``plan`` is the original, unfiltered plan so skipped rows show up."""
    out: list[ReportRow] = []
    for item in plan.items:
        row, existing = item.row, item.existing
        name = existing.name if existing is not None else row.name
        old_r = None if existing is None else existing.regular_price
        old_w = None if existing is None else existing.website_price
        new_r, new_w = row.regular_price, row.website_price
        if item.kind is Kind.NEW:
            status = (
                T.UPDATE_STATUS_SKIPPED
                if row.row in skipped_new
                else T.UPDATE_STATUS_CREATED
            )
        elif item.kind is Kind.CONFLICT:
            if decisions.get(row.row, Decision.SKIP) is Decision.UPDATE:
                status = (
                    T.UPDATE_STATUS_RESTORED
                    if item.restores
                    else T.UPDATE_STATUS_UPDATED
                )
            else:
                status = T.UPDATE_STATUS_SKIPPED
        else:
            status = T.UPDATE_STATUS_UNCHANGED
            new_r, new_w = old_r, old_w
        if status == T.UPDATE_STATUS_SKIPPED:
            new_r = new_w = None
        out.append(ReportRow(name, status, old_r, new_r, old_w, new_w))
    return tuple(out)


def changed_only(rows: Iterable[ReportRow]) -> tuple[ReportRow, ...]:
    return tuple(r for r in rows if r.status != T.UPDATE_STATUS_UNCHANGED)


def _cell(value: Decimal | None) -> str:
    return "" if value is None else format_decimal_exact(value)


def write_report_csv(rows: Iterable[ReportRow], path: Path) -> int:
    """UTF-8 with BOM (Excel); text cells escaped like ``csv_export``."""
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=",", lineterminator="\n")
        writer.writerow(
            (
                "product_name",
                "status",
                "old_regular_price",
                "new_regular_price",
                "old_website_price",
                "new_website_price",
            )
        )
        for r in rows:
            writer.writerow(
                (
                    _safe_text_cell(r.name),
                    _safe_text_cell(r.status),
                    _cell(r.old_regular),
                    _cell(r.new_regular),
                    _cell(r.old_website),
                    _cell(r.new_website),
                )
            )
            count += 1
    return count
