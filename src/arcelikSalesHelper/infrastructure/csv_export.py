"""CSV export for the editable product catalog."""

from __future__ import annotations

import csv
from pathlib import Path
from collections.abc import Iterable

from arcelikSalesHelper.domain.formatting import format_decimal_exact
from arcelikSalesHelper.domain.products import Product


_FORMULA_PREFIXES = "=+-@\t\r"


def _safe_text_cell(value: str) -> str:
    """Escape spreadsheet formulas and preserve an escape marker for import."""
    marker = len(value) - len(value.lstrip())
    if value[marker:marker + 1] in _FORMULA_PREFIXES:
        return "'" + value
    if value.startswith("'"):
        marker = len(value) - len(value.lstrip("'"))
        if value[marker:marker + 1] in _FORMULA_PREFIXES:
            return "'" + value
    return value


def export_products_csv(products: Iterable[Product], path: Path) -> int:
    """Write products in the existing import-compatible price/quantity format."""
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=",", lineterminator="\n")
        writer.writerow(("product_name", "regular_price", "website_discounted_price", "quantity"))
        for product in products:
            writer.writerow((
                _safe_text_cell(product.name),
                format_decimal_exact(product.regular_price),
                format_decimal_exact(product.website_price),
                "" if product.quantity is None else product.quantity,
            ))
            count += 1
    return count
