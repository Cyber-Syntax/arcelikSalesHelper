"""Maps scraped rows onto the existing CSV-import plan/apply pipeline."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.domain.products import (
    MAX_NAME_LENGTH,
    Product,
    name_key,
)
from arcelikSalesHelper.infrastructure.scrapper.models import ScrapedProduct

from .csv_import import (
    Decision,
    ImportFormat,
    ImportPlan,
    Kind,
    ParsedCsv,
    ParsedRow,
    RowError,
)

log = logging.getLogger(__name__)
ZERO = Decimal(0)


@dataclass(frozen=True)
class EffectivePrices:
    regular: Decimal
    website: Decimal
    warnings: tuple[str, ...]


def resolve_effective_prices(
    scraped: ScrapedProduct,
    existing: Product | None,
    *,
    partial: bool = False,
) -> EffectivePrices:
    """An empty scraped price keeps the catalog value (0 for a new product).

    Warnings are only raised when there is a non-zero catalog value being
    kept, so ordinary non-discounted products stay quiet.
    """
    warnings: list[str] = []
    no_regular = scraped.regular_price is None
    no_website = scraped.website_price is None
    if existing is None:
        regular = (
            ZERO if scraped.regular_price is None else scraped.regular_price
        )
        website = (
            ZERO if scraped.website_price is None else scraped.website_price
        )
        if no_regular:
            warnings.append(T.UPDATE_WARN_NEW_NO_REGULAR)
    else:
        regular = (
            existing.regular_price
            if scraped.regular_price is None
            else scraped.regular_price
        )
        website = (
            existing.website_price
            if scraped.website_price is None
            else scraped.website_price
        )
        kept_regular = no_regular and existing.regular_price != ZERO
        kept_website = no_website and existing.website_price != ZERO
        if no_regular and no_website:
            if kept_regular or kept_website:
                warnings.append(T.UPDATE_WARN_NO_PRICE)
        else:
            if kept_regular:
                warnings.append(T.UPDATE_WARN_NO_REGULAR)
            if kept_website:
                warnings.append(T.UPDATE_WARN_NO_WEBSITE)
        if existing.archived:
            warnings.append(T.UPDATE_WARN_ARCHIVED)
    if partial:
        warnings.append(T.UPDATE_WARN_PARTIAL)
    return EffectivePrices(regular, website, tuple(warnings))


@dataclass(frozen=True)
class ScrapeBuild:
    parsed: ParsedCsv
    scraped: int
    duplicate_names: int
    without_price: int


def build_scrape_parsed(
    scraped: Sequence[ScrapedProduct],
    existing_by_key: Mapping[str, Product],
    *,
    partial: bool = False,
) -> ScrapeBuild:
    rows: list[ParsedRow] = []
    errors: list[RowError] = []
    seen: dict[str, int] = {}
    duplicates = 0
    without_price = 0
    for number, product in enumerate(scraped, start=2):  # header is row 1
        name = " ".join(product.name.split())
        if not name:
            errors.append(
                RowError(number, "product_name", T.VAL_NAME_REQUIRED)
            )
            continue
        if len(name) > MAX_NAME_LENGTH:
            errors.append(
                RowError(
                    number,
                    "product_name",
                    T.val_name_too_long(MAX_NAME_LENGTH),
                )
            )
            continue
        key = name_key(name)
        if key in seen:
            duplicates += 1
            log.info(
                "duplicate scraped name dropped: row %d repeats row %d",
                number,
                seen[key],
            )
            continue
        seen[key] = number
        effective = resolve_effective_prices(
            product, existing_by_key.get(key), partial=partial
        )
        if product.regular_price is None and product.website_price is None:
            without_price += 1
        rows.append(
            ParsedRow(
                number,
                name,
                key,
                effective.regular,
                effective.website,
                None,
                effective.warnings,
            )
        )
    parsed = ParsedCsv(ImportFormat.SCRAPE, tuple(rows), tuple(errors))
    return ScrapeBuild(parsed, len(scraped), duplicates, without_price)


# ---- decisions -----------------------------------------------------------


def default_decisions(plan: ImportPlan) -> dict[int, Decision]:
    """Conflicts default to Skip: no existing price changes unless chosen."""
    return {item.row.row: Decision.SKIP for item in plan.conflicts}


def without_rows(plan: ImportPlan, skipped: Collection[int]) -> ImportPlan:
    """Drop NEW rows the employee unticked (conflicts use decisions)."""
    items = tuple(
        i
        for i in plan.items
        if not (i.kind is Kind.NEW and i.row.row in skipped)
    )
    return replace(plan, items=items)


@dataclass(frozen=True)
class ChoiceCounts:
    updated: int
    created: int
    restored: int

    @property
    def total(self) -> int:
        return self.updated + self.created + self.restored


def count_choices(
    plan: ImportPlan, decisions: Mapping[int, Decision]
) -> ChoiceCounts:
    updated = created = restored = 0
    for item in plan.items:
        if item.kind is Kind.NEW:
            created += 1
        elif (
            item.kind is Kind.CONFLICT
            and decisions.get(item.row.row, Decision.SKIP) is Decision.UPDATE
        ):
            if item.restores:
                restored += 1
            else:
                updated += 1
    return ChoiceCounts(updated, created, restored)


@dataclass(frozen=True)
class ScrapePlanInfo:
    scraped: int
    new: int
    conflicts: int
    unchanged: int
    without_price: int
    duplicate_names: int
    errors: int


def plan_info(build: ScrapeBuild, plan: ImportPlan) -> ScrapePlanInfo:
    kinds = Counter(i.kind for i in plan.items)
    return ScrapePlanInfo(
        build.scraped,
        kinds[Kind.NEW],
        kinds[Kind.CONFLICT],
        kinds[Kind.UNCHANGED],
        build.without_price,
        build.duplicate_names,
        len(plan.errors),
    )
