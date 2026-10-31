"""Pure parsing of arcelik.com.tr HTML/XML. All selectors live here."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

from selectolax.lexbor import LexborHTMLParser

from arcelikSalesHelper.domain.money import parse_money_ex
from arcelikSalesHelper.domain.result import Ok

from .models import BASE_URL, ScrapedProduct

LABEL_SUFFIX = " ürün detaylarını incele"
SEL_CARD = "div.prd-inner"
SEL_LINK = ".prd-detail a[href]"
SEL_LINK_FALLBACK = "a.js-prd-url"
SEL_TITLE = ".prd-name .t"
SEL_CODE = "[data-product-code]"
SEL_REGULAR = ".prd-price > .prc"
SEL_DISCOUNTED = ".prd-row-price-third .prc-third"

_NUMBER = re.compile(r"\d[\d.,]*")
_HAS_DIGIT = re.compile(r"\d")
_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.DOTALL)


@dataclass(frozen=True)
class ListingPage:
    products: tuple[ScrapedProduct, ...]
    price_failures: int = 0  # price text with digits that did not parse
    nameless_cards: int = 0


def parse_price(text: str) -> Decimal | None:
    """First numeric token through the shared money parser; None if none."""
    match = _NUMBER.search(text.replace("\xa0", " "))
    if match is None:
        return None
    result = parse_money_ex(match.group().rstrip(".,"))
    return result.value.value if isinstance(result, Ok) else None


def _price(node: Any) -> tuple[Decimal | None, bool]:
    if node is None:
        return None, False
    text = node.text(strip=True)
    value = parse_price(text)
    return value, value is None and bool(_HAS_DIGIT.search(text))


def _clean(text: str) -> str:
    return " ".join(text.split())


def parse_listing(html: str, base_url: str = BASE_URL) -> ListingPage:
    """Cards of one listing page, deduplicated by product URL.

    An empty result means "page has no cards" (end of pagination). A page that
    failed to load never reaches this function: the crawler sees ``None``.
    """
    found: dict[str, ScrapedProduct] = {}
    price_failures = 0
    nameless = 0
    for card in LexborHTMLParser(html).css(SEL_CARD):
        link = card.css_first(SEL_LINK)
        if link is None:
            link = card.css_first(SEL_LINK_FALLBACK)
        href = None if link is None else link.attributes.get("href")
        if link is None or not href:
            continue
        url = urljoin(base_url, href).split("?")[0]
        if url in found:
            continue
        label = _clean(
            (link.attributes.get("aria-label") or "")
            .strip()
            .removesuffix(LABEL_SUFFIX)
        )
        title_node = card.css_first(SEL_TITLE)
        title = _clean(title_node.text(strip=True)) if title_node else ""
        name = label or title
        if not name:
            nameless += 1
            continue
        regular, bad_regular = _price(card.css_first(SEL_REGULAR))
        website, bad_website = _price(card.css_first(SEL_DISCOUNTED))
        price_failures += int(bad_regular) + int(bad_website)
        code_node = card.css_first(SEL_CODE)
        code = (
            (code_node.attributes.get("data-product-code") or "")
            if code_node is not None
            else ""
        )
        found[url] = ScrapedProduct(
            name, regular, website, code=code, title=title, url=url
        )
    return ListingPage(tuple(found.values()), price_failures, nameless)


# ---- sitemap ---------------------------------------------------------------


def sitemap_locs(xml: str) -> list[str]:
    return [unescape(m) for m in _LOC.findall(xml)]


def product_sitemap_urls(index_xml: str) -> list[str]:
    return [u for u in sitemap_locs(index_xml) if "PRODUCT" in u]


def category_slugs(product_urls: Iterable[str]) -> list[str]:
    """Category = first segment of two-segment product paths."""
    slugs: set[str] = set()
    for url in product_urls:
        parts = urlparse(url).path.strip("/").split("/")
        if len(parts) == 2 and parts[0]:
            slugs.add(parts[0])
    return sorted(slugs)
