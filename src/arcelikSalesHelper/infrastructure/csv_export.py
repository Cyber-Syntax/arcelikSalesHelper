"""CSV export for the editable product catalog."""

from __future__ import annotations

import csv
from pathlib import Path
from collections.abc import Iterable

from arcelikSalesHelper.domain.formatting import format_decimal_exact
from arcelikSalesHelper.domain.products import Product


def export_products_csv(products: Iterable[Product], path: Path) -> int:
    """Write products in the existing import-compatible price/quantity format."""
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=",", lineterminator="\n")
        writer.writerow(("product_name", "regular_price", "website_discounted_price", "quantity"))
        for product in products:
            writer.writerow((
                product.name,
                format_decimal_exact(product.regular_price),
                format_decimal_exact(product.website_price),
                "" if product.quantity is None else product.quantity,
            ))
            count += 1
    return count
