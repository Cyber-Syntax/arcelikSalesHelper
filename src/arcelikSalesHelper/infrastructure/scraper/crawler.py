"""Polite async crawl: sitemap -> category slugs -> paginated listings."""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from arcelikSalesHelper import strings as T

from . import parser
from .models import (
    ScrapeConfig,
    ScrapedProduct,
    ScrapeError,
    ScrapeErrorCode,
    ScrapeOutcome,
    ScrapeProgress,
)

log = logging.getLogger(__name__)

ProgressCallback = Callable[[ScrapeProgress], None]
SleepFn = Callable[[float], Awaitable[None]]
JitterFn = Callable[[float, float], float]


class HttpResponse(Protocol):
    status_code: int

    @property
    def text(self) -> str: ...


class HttpSession(Protocol):
    async def get(self, url: str) -> HttpResponse: ...


class _Blocked(Exception):
    pass


class _Cancelled(Exception):
    pass


class _Unreachable(Exception):
    pass


@dataclass
class _Stats:
    done: int = 0
    failed_categories: int = 0
    failed_requests: int = 0
    price_failures: int = 0


@dataclass
class _CategoryResult:
    products: dict[str, ScrapedProduct] = field(default_factory=dict)
    price_failures: int = 0
    loaded: bool = False  # first page loaded


def _curl_session(config: ScrapeConfig) -> Any:
    """Browser-impersonating session. No custom User-Agent on purpose."""
    from curl_cffi.requests import AsyncSession

    return AsyncSession(
        impersonate="chrome",
        headers={"Accept-Language": "tr-TR,tr;q=0.9"},
        timeout=config.timeout,
        allow_redirects=True,
    )


def filter_categories(
    slugs: Iterable[str],
    allow: frozenset[str] = frozenset(),
    block: frozenset[str] = frozenset(),
) -> list[str]:
    """Empty allowlist = everything; the blocklist always wins."""
    return [s for s in slugs if (not allow or s in allow) and s not in block]


class _Fetcher:
    def __init__(
        self,
        session: HttpSession,
        config: ScrapeConfig,
        cancel: threading.Event,
        sleep: SleepFn,
        jitter: JitterFn,
        stats: _Stats,
    ) -> None:
        self._session = session
        self._config = config
        self._cancel = cancel
        self._sleep = sleep
        self._jitter = jitter
        self._stats = stats
        self._sem = asyncio.Semaphore(config.concurrency)
        self._blocked_streak = 0

    def _check(self) -> None:
        if self._cancel.is_set():
            raise _Cancelled

    async def _nap(self, seconds: float) -> None:
        """Sleep in short slices so cancellation is prompt."""
        remaining = seconds
        while remaining > 0:
            self._check()
            step = min(0.5, remaining)
            await self._sleep(step)
            remaining -= step

    async def get(self, url: str) -> str | None:
        cfg = self._config
        for attempt in range(cfg.retries):
            self._check()
            status: int | None = None
            text: str | None = None
            async with self._sem:
                await self._nap(self._jitter(cfg.min_delay, cfg.max_delay))
                self._check()
                try:
                    response = await self._session.get(url)
                    status = response.status_code
                    text = response.text if status == 200 else None
                except Exception as exc:  # transport layer: retry
                    status = None
                    log.warning("request error: %s", type(exc).__name__)
            if status == 200 and text is not None:
                self._blocked_streak = 0
                return text
            if status in (403, 429):
                self._blocked_streak += 1
                if self._blocked_streak >= cfg.blocked_threshold:
                    raise _Blocked
            else:
                self._blocked_streak = 0
                if status is not None and status < 500:
                    log.warning("HTTP %s (not retried)", status)
                    self._stats.failed_requests += 1
                    return None
            await self._nap(2**attempt * 2)
        self._stats.failed_requests += 1
        return None


async def _discover(fetcher: _Fetcher, config: ScrapeConfig) -> list[str]:
    index = await fetcher.get(f"{config.base_url}/sitemap.xml")
    if index is None:
        raise _Unreachable
    urls: set[str] = set()
    for loc in parser.product_sitemap_urls(index):
        xml = await fetcher.get(loc)
        if xml:
            urls.update(parser.sitemap_locs(xml))
    return parser.category_slugs(urls)


async def _crawl_category(
    fetcher: _Fetcher, config: ScrapeConfig, slug: str
) -> _CategoryResult:
    result = _CategoryResult()
    for page in range(config.max_pages):
        url = f"{config.base_url}/{slug}" + (f"?page={page}" if page else "")
        html = await fetcher.get(url)
        if html is None:
            break  # failed load: counted by the fetcher
        if page == 0:
            result.loaded = True
        listing = parser.parse_listing(html, config.base_url)
        result.price_failures += listing.price_failures
        fresh = [p for p in listing.products if p.url not in result.products]
        if not fresh:  # no cards, or a repeated page: legitimate end
            break
        for product in fresh:
            result.products[product.url] = product
    return result


async def _run_categories(
    slugs: list[str],
    fetcher: _Fetcher,
    config: ScrapeConfig,
    stats: _Stats,
    products: dict[str, ScrapedProduct],
    report: ProgressCallback,
) -> None:
    total = len(slugs)

    async def one(slug: str) -> None:
        try:
            result = await _crawl_category(fetcher, config, slug)
        except (_Blocked, _Cancelled):
            raise
        except Exception:
            log.exception("category %s failed", slug)
            stats.failed_categories += 1
        else:
            stats.price_failures += result.price_failures
            if not result.loaded:
                stats.failed_categories += 1
            for product in result.products.values():
                products.setdefault(product.url, product)
            log.info("category %s: %d products", slug, len(result.products))
        stats.done += 1
        report(ScrapeProgress(slug, stats.done, total, len(products)))

    tasks = [asyncio.create_task(one(s)) for s in slugs]
    if not tasks:
        return
    done, pending = await asyncio.wait(
        tasks, return_when=asyncio.FIRST_EXCEPTION
    )
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        exc = task.exception()
        if exc is not None:
            raise exc


def _ignore(_progress: ScrapeProgress) -> None:
    return None


async def crawl(
    config: ScrapeConfig | None = None,
    on_progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
    *,
    session_factory: Callable[[ScrapeConfig], Any] = _curl_session,
    sleep: SleepFn = asyncio.sleep,
    jitter: JitterFn = random.uniform,
) -> ScrapeOutcome:
    """Run one crawl. Never raises for network/blocking problems; an
    ImportError from curl_cffi propagates so the worker can report it.
    """
    cfg = config or ScrapeConfig()
    stop = cancel or threading.Event()
    report = on_progress or _ignore
    started = time.monotonic()
    stats = _Stats()
    products: dict[str, ScrapedProduct] = {}
    total = 0
    error: ScrapeError | None = None
    cancelled = False
    log.info("scrape started")
    try:
        async with session_factory(cfg) as session:
            fetcher = _Fetcher(session, cfg, stop, sleep, jitter, stats)
            slugs = filter_categories(
                await _discover(fetcher, cfg),
                cfg.category_allowlist,
                cfg.category_blocklist,
            )
            total = len(slugs)
            report(ScrapeProgress("", 0, total, 0))
            await _run_categories(slugs, fetcher, cfg, stats, products, report)
    except _Cancelled:
        cancelled = True
    except _Blocked:
        error = ScrapeError(ScrapeErrorCode.BLOCKED, T.UPDATE_BLOCKED)
    except _Unreachable:
        error = ScrapeError(ScrapeErrorCode.NETWORK, T.UPDATE_NETWORK)
    if error is None and not cancelled and not products:
        error = ScrapeError(ScrapeErrorCode.NO_PRODUCTS, T.UPDATE_NO_PRODUCTS)
    outcome = ScrapeOutcome(
        products=tuple(products.values()),
        categories_total=total,
        categories_done=stats.done,
        categories_failed=stats.failed_categories,
        failed_requests=stats.failed_requests,
        price_failures=stats.price_failures,
        elapsed_seconds=time.monotonic() - started,
        cancelled=cancelled,
        error=error,
    )
    log.info(
        "scrape finished: %d products, %d/%d categories, %d failed "
        "categories, %d failed requests, %.1fs, cancelled=%s, error=%s",
        len(outcome.products),
        outcome.categories_done,
        outcome.categories_total,
        outcome.categories_failed,
        outcome.failed_requests,
        outcome.elapsed_seconds,
        cancelled,
        None if error is None else error.code.value,
    )
    return outcome
