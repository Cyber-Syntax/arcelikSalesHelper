"""Polite async crawl: sitemap -> category slugs -> paginated listings."""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
import uuid
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
    capped_categories: int = 0
    nameless_cards: int = 0
    requests: int = 0
    retries: int = 0
    pages: int = 0
    parse_seconds: float = 0.0
    discovery_seconds: float = 0.0


@dataclass
class _CategoryResult:
    products: dict[str, ScrapedProduct] = field(default_factory=dict)
    price_failures: int = 0
    loaded: bool = False  # first page loaded
    capped: bool = False
    nameless: int = 0


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
        run_id: str,
    ) -> None:
        self._session = session
        self._config = config
        self._cancel = cancel
        self._sleep = sleep
        self._jitter = jitter
        self._stats = stats
        self._run_id = run_id
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

    async def get(self, url: str, *, context: str = "request") -> str | None:
        cfg = self._config
        for attempt in range(cfg.retries):
            self._check()
            self._stats.requests += 1
            status: int | None = None
            text: str | None = None
            request_started = time.monotonic()
            async with self._sem:
                await self._nap(self._jitter(cfg.min_delay, cfg.max_delay))
                self._check()
                try:
                    response = await self._session.get(url)
                    status = response.status_code
                    text = response.text if status == 200 else None
                except Exception as exc:  # transport layer: retry
                    status = None
                    log.warning(
                        "[%s] request error url=%s context=%s attempt=%d/%d "
                        "error=%s",
                        self._run_id,
                        url,
                        context,
                        attempt + 1,
                        cfg.retries,
                        type(exc).__name__,
                    )
            elapsed = time.monotonic() - request_started
            size = 0 if text is None else len(text.encode("utf-8"))
            log_level = logging.WARNING if elapsed >= 5 else logging.DEBUG
            log.log(
                log_level,
                "[%s] request url=%s context=%s attempt=%d/%d status=%s "
                "bytes=%d elapsed=%.3fs",
                self._run_id,
                url,
                context,
                attempt + 1,
                cfg.retries,
                status,
                size,
                elapsed,
            )
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
                    log.warning(
                        "[%s] request failed url=%s context=%s status=%s "
                        "(not retried)",
                        self._run_id,
                        url,
                        context,
                        status,
                    )
                    self._stats.failed_requests += 1
                    return None
            if attempt < cfg.retries - 1:
                backoff = 2**attempt * 2
                self._stats.retries += 1
                log.warning(
                    "[%s] request retry scheduled url=%s context=%s "
                    "after=%.1fs",
                    self._run_id,
                    url,
                    context,
                    backoff,
                )
                await self._nap(backoff)
        self._stats.failed_requests += 1
        return None


async def _discover(
    fetcher: _Fetcher, config: ScrapeConfig, run_id: str, stats: _Stats
) -> list[str]:
    started = time.monotonic()
    index = await fetcher.get(
        f"{config.base_url}/sitemap.xml", context="sitemap-index"
    )
    if index is None:
        raise _Unreachable
    urls: set[str] = set()
    sitemap_urls = parser.product_sitemap_urls(index)
    log.info(
        "[%s] sitemap discovery: %d product sitemaps",
        run_id,
        len(sitemap_urls),
    )
    for sitemap_number, loc in enumerate(sitemap_urls, 1):
        xml = await fetcher.get(
            loc, context=f"sitemap-{sitemap_number}/{len(sitemap_urls)}"
        )
        if xml:
            urls.update(parser.sitemap_locs(xml))
    slugs = parser.category_slugs(urls)
    stats.discovery_seconds = time.monotonic() - started
    log.info(
        "[%s] sitemap discovery finished: %d product urls, %d categories, "
        "%.3fs",
        run_id,
        len(urls),
        len(slugs),
        stats.discovery_seconds,
    )
    return slugs


async def _crawl_category(
    fetcher: _Fetcher,
    config: ScrapeConfig,
    slug: str,
    run_id: str,
    report: ProgressCallback,
    stats: _Stats,
    total: int,
    products: dict[str, ScrapedProduct],
) -> _CategoryResult:
    result = _CategoryResult()
    category_started = time.monotonic()
    for page in range(config.max_pages):
        url = f"{config.base_url}/{slug}" + (f"?page={page}" if page else "")
        log.info(
            "[%s] category page started category=%s page=%d",
            run_id,
            slug,
            page,
        )
        report(
            ScrapeProgress(
                slug,
                stats.done,
                total,
                len(products),
                "fetch",
                page,
            )
        )
        html = await fetcher.get(url, context=f"category={slug} page={page}")
        if html is None:
            log.warning(
                "[%s] category page failed category=%s page=%d",
                run_id,
                slug,
                page,
            )
            break  # failed load: counted by the fetcher
        if page == 0:
            result.loaded = True
        parse_started = time.monotonic()
        listing = parser.parse_listing(html, config.base_url)
        parse_elapsed = time.monotonic() - parse_started
        stats.parse_seconds += parse_elapsed
        stats.pages += 1
        result.price_failures += listing.price_failures
        result.nameless += listing.nameless_cards
        fresh = [p for p in listing.products if p.url not in result.products]
        log_level = logging.WARNING if parse_elapsed >= 5 else logging.DEBUG
        log.log(
            log_level,
            "[%s] category page parsed category=%s page=%d bytes=%d "
            "cards=%d fresh=%d parse=%.3fs price_failures=%d nameless=%d",
            run_id,
            slug,
            page,
            len(html.encode("utf-8")),
            len(listing.products),
            len(fresh),
            parse_elapsed,
            listing.price_failures,
            listing.nameless_cards,
        )
        report(
            ScrapeProgress(
                slug,
                stats.done,
                total,
                len(products) + len(fresh),
                "parse",
                page,
                len(fresh),
            )
        )
        if not fresh:  # no cards, or a repeated page: legitimate end
            log.info(
                "[%s] category page ended category=%s page=%d reason=%s",
                run_id,
                slug,
                page,
                "empty" if not listing.products else "repeated",
            )
            break
        for product in fresh:
            result.products[product.url] = product
    else:  # loop ended without a break: the page cap truncated the category
        result.capped = True
        log.warning(
            "[%s] category %s hit the %d page cap",
            run_id,
            slug,
            config.max_pages,
        )
    log.info(
        "[%s] category finished category=%s products=%d pages=%d elapsed=%.3fs",
        run_id,
        slug,
        len(result.products),
        page + 1,
        time.monotonic() - category_started,
    )
    return result


async def _run_categories(
    slugs: list[str],
    fetcher: _Fetcher,
    config: ScrapeConfig,
    stats: _Stats,
    products: dict[str, ScrapedProduct],
    report: ProgressCallback,
    run_id: str,
) -> None:
    total = len(slugs)

    async def one(slug: str) -> None:
        try:
            result = await _crawl_category(
                fetcher, config, slug, run_id, report, stats, total, products
            )
        except (_Blocked, _Cancelled):
            raise
        except Exception:
            log.exception("[%s] category %s failed", run_id, slug)
            stats.failed_categories += 1
        else:
            stats.price_failures += result.price_failures
            stats.nameless_cards += result.nameless
            stats.capped_categories += int(result.capped)
            if not result.loaded:
                stats.failed_categories += 1
            for product in result.products.values():
                products.setdefault(product.url, product)
            log.info(
                "[%s] category %s: %d products",
                run_id,
                slug,
                len(result.products),
            )
        stats.done += 1
        report(
            ScrapeProgress(
                slug,
                stats.done,
                total,
                len(products),
                "category",
            )
        )

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
    run_id = uuid.uuid4().hex[:8]
    stats = _Stats()
    products: dict[str, ScrapedProduct] = {}
    total = 0
    error: ScrapeError | None = None
    cancelled = False
    log.info("[%s] scrape started", run_id)
    try:
        async with session_factory(cfg) as session:
            fetcher = _Fetcher(
                session, cfg, stop, sleep, jitter, stats, run_id
            )
            slugs = filter_categories(
                await _discover(fetcher, cfg, run_id, stats),
                cfg.category_allowlist,
                cfg.category_blocklist,
            )
            total = len(slugs)
            report(ScrapeProgress("", 0, total, 0))
            await _run_categories(
                slugs, fetcher, cfg, stats, products, report, run_id
            )
    except _Cancelled:
        cancelled = True
        log.info("[%s] scrape cancelled", run_id)
    except _Blocked:
        error = ScrapeError(ScrapeErrorCode.BLOCKED, T.UPDATE_BLOCKED)
        log.warning("[%s] scrape blocked", run_id)
    except _Unreachable:
        error = ScrapeError(ScrapeErrorCode.NETWORK, T.UPDATE_NETWORK)
        log.warning("[%s] scrape unreachable", run_id)
    if error is None and not cancelled and not products:
        error = ScrapeError(ScrapeErrorCode.NO_PRODUCTS, T.UPDATE_NO_PRODUCTS)
    outcome = ScrapeOutcome(
        products=tuple(products.values()),
        categories_total=total,
        categories_done=stats.done,
        capped_categories=stats.capped_categories,
        nameless_cards=stats.nameless_cards,
        categories_failed=stats.failed_categories,
        failed_requests=stats.failed_requests,
        price_failures=stats.price_failures,
        elapsed_seconds=time.monotonic() - started,
        cancelled=cancelled,
        error=error,
    )
    log.info(
        "[%s] scrape finished: %d products, %d/%d categories, %d failed "
        "categories, %d failed requests, %.1fs, cancelled=%s, error=%s",
        run_id,
        len(outcome.products),
        outcome.categories_done,
        outcome.categories_total,
        outcome.categories_failed,
        outcome.failed_requests,
        outcome.elapsed_seconds,
        cancelled,
        None if error is None else error.code.value,
    )
    log.info(
        "[%s] scrape diagnostics: requests=%d retries=%d pages=%d "
        "discovery=%.3fs parse=%.3fs price_failures=%d nameless=%d capped=%d",
        run_id,
        stats.requests,
        stats.retries,
        stats.pages,
        stats.discovery_seconds,
        stats.parse_seconds,
        stats.price_failures,
        stats.nameless_cards,
        stats.capped_categories,
    )
    return outcome
