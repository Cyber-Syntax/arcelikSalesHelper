import asyncio
from dataclasses import dataclass
from decimal import Decimal

from arcelikSalesHelper.infrastructure.scrapper.crawler import (
    crawl,
    filter_categories,
)
from arcelikSalesHelper.infrastructure.scrapper.models import (
    BASE_URL,
    ScrapeConfig,
    ScrapeErrorCode,
)
from arcelikSalesHelper.infrastructure.scrapper.parser import (
    category_slugs,
    parse_listing,
    parse_price,
    product_sitemap_urls,
)


def card(path, label, regular="", discounted="", code="C1"):
    reg = f'<span class="prc">{regular}</span>' if regular else ""
    disc = f'<span class="prc-third">{discounted}</span>' if discounted else ""
    return (
        '<div class="prd-inner">'
        f'<div class="prd-detail"><a class="js-prd-url" href="{path}?x=1" '
        f'aria-label="{label} ürün detaylarını incele"></a></div>'
        f'<div class="prd-name"><span class="t">{label}</span></div>'
        f'<div class="prd-price" data-product-code="{code}">{reg}</div>'
        f'<div class="prd-row-price-third">{disc}</div>'
        "</div>"
    )


def test_parse_listing_prices_suffix_and_dedupe():
    html = (
        card("/buzdolabi/a", "Arçelik A 1", "60.999,00 TL", "54.999,00 TL")
        + card("/buzdolabi/b", "ek garanti 2 yıl", "1.299,00 TL")
        + card("/buzdolabi/c", "Fiyatsız ürün")
        + card("/buzdolabi/a", "Arçelik A 1", "1,00 TL")  # duplicate URL
    )
    page = parse_listing(html)
    a, garanti, none = page.products
    assert len(page.products) == 3
    assert a.name == "Arçelik A 1"
    assert a.url == f"{BASE_URL}/buzdolabi/a"
    assert (a.regular_price, a.website_price) == (
        Decimal("60999.00"),
        Decimal("54999.00"),
    )
    assert garanti.website_price is None
    assert none.regular_price is None and none.website_price is None
    assert a.code == "C1"


def test_parse_price_variants():
    assert parse_price("1.234.567,89 TL") == Decimal("1234567.89")
    assert parse_price("54.999,00\xa0TL") == Decimal("54999.00")
    assert parse_price("Fiyat yok") is None


def test_sitemap_helpers():
    index = (
        "<loc>https://x/sitemap-PRODUCT-1.xml?a=1&amp;b=2</loc>"
        "<loc>https://x/sitemap-CATEGORY.xml</loc>"
    )
    assert product_sitemap_urls(index) == [
        "https://x/sitemap-PRODUCT-1.xml?a=1&b=2"
    ]
    urls = [
        f"{BASE_URL}/buzdolabi/p1",
        f"{BASE_URL}/buzdolabi/p2",
        f"{BASE_URL}/klima/p3",
        f"{BASE_URL}/blog",
        f"{BASE_URL}/a/b/c",
    ]
    assert category_slugs(urls) == ["buzdolabi", "klima"]


def test_filter_categories_blocklist_wins():
    slugs = ["a", "b", "c"]
    assert filter_categories(slugs) == slugs
    assert filter_categories(slugs, frozenset({"a", "b"})) == ["a", "b"]
    assert filter_categories(
        slugs, frozenset({"a", "b"}), frozenset({"b"})
    ) == ["a"]


# ---- crawler with a fake session ---------------------------------------


@dataclass
class FakeResponse:
    status_code: int
    text: str = ""


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    async def get(self, url):
        self.calls.append(url)
        return self.pages.get(url, FakeResponse(404))


class FakeFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self, _config):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return None


async def _no_sleep(_seconds):
    return None


def _run(session, config=None):
    return asyncio.run(
        crawl(
            config,
            session_factory=FakeFactory(session),
            sleep=_no_sleep,
            jitter=lambda _a, _b: 0.0,
        )
    )


SITEMAP = f"{BASE_URL}/sitemap.xml"
PRODUCT_MAP = "https://x/sitemap-PRODUCT-1.xml"


def _site(extra):
    pages = {
        SITEMAP: FakeResponse(200, f"<loc>{PRODUCT_MAP}</loc>"),
        PRODUCT_MAP: FakeResponse(200, f"<loc>{BASE_URL}/buzdolabi/p1</loc>"),
    }
    pages.update(extra)
    return pages


def test_pagination_stops_on_repeated_page():
    pages = _site(
        {
            f"{BASE_URL}/buzdolabi": FakeResponse(
                200, card("/buzdolabi/a", "A", "100,00 TL")
            ),
            f"{BASE_URL}/buzdolabi?page=1": FakeResponse(
                200, card("/buzdolabi/b", "B", "200,00 TL")
            ),
            f"{BASE_URL}/buzdolabi?page=2": FakeResponse(
                200, card("/buzdolabi/b", "B", "200,00 TL")
            ),
        }
    )
    session = FakeSession(pages)
    outcome = _run(session)
    assert [p.name for p in outcome.products] == ["A", "B"]
    assert outcome.complete
    assert f"{BASE_URL}/buzdolabi?page=3" not in session.calls


def test_repeated_403_aborts_as_blocked():
    session = FakeSession({SITEMAP: FakeResponse(403)})
    outcome = _run(session)
    assert outcome.error is not None
    assert outcome.error.code is ScrapeErrorCode.BLOCKED
    assert len(session.calls) == 3  # ScrapeConfig.blocked_threshold


def test_zero_products_is_a_failure():
    pages = _site({f"{BASE_URL}/buzdolabi": FakeResponse(200, "<html/>")})
    outcome = _run(FakeSession(pages))
    assert outcome.error is not None
    assert outcome.error.code is ScrapeErrorCode.NO_PRODUCTS


def test_failed_category_makes_outcome_incomplete():
    pages = _site(
        {f"{BASE_URL}/buzdolabi": FakeResponse(404)}  # not retried
    )
    outcome = _run(FakeSession(pages), ScrapeConfig())
    assert not outcome.complete
    assert outcome.categories_failed == 1
