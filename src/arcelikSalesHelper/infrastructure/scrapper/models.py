from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

BASE_URL = "https://www.arcelik.com.tr"


@dataclass(frozen=True)
class ScrapedProduct:
    name: str
    regular_price: Decimal | None
    website_price: Decimal | None
    code: str = ""  # logging only
    title: str = ""  # logging only
    url: str = ""  # logging / dedupe only


class ScrapeErrorCode(Enum):
    BLOCKED = "blocked"
    NETWORK = "network"
    PARSE = "parse"
    CANCELLED = "cancelled"
    NO_PRODUCTS = "no_products"


@dataclass(frozen=True)
class ScrapeError:
    code: ScrapeErrorCode
    message: str


@dataclass(frozen=True)
class ScrapeProgress:
    category: str
    categories_done: int
    categories_total: int
    products_found: int


@dataclass(frozen=True)
class ScrapeConfig:
    base_url: str = BASE_URL
    concurrency: int = 2
    min_delay: float = 0.5
    max_delay: float = 1.5
    retries: int = 4
    timeout: float = 20.0
    max_pages: int = 200
    blocked_threshold: int = 3  # consecutive 403/429 before aborting
    # Extension point for the later whitelist/blacklist UI. Empty allowlist
    # means "all categories"; the blocklist always wins.
    category_allowlist: frozenset[str] = frozenset()
    category_blocklist: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ScrapeOutcome:
    products: tuple[ScrapedProduct, ...]
    categories_total: int
    categories_done: int
    categories_failed: int
    failed_requests: int
    price_failures: int
    elapsed_seconds: float
    cancelled: bool = False
    error: ScrapeError | None = None

    @property
    def complete(self) -> bool:
        """True only when nothing was cancelled, failed or skipped by error."""
        return (
            self.error is None
            and not self.cancelled
            and self.categories_failed == 0
            and self.failed_requests == 0
        )
