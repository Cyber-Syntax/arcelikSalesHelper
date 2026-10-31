"""Scraper package. Importing it must stay free of third-party imports.

``parser`` (selectolax) and ``crawler`` (curl_cffi, lazily) are imported
explicitly by the worker, so a missing native library cannot stop the app.
"""

from .models import (
    BASE_URL,
    ScrapeConfig,
    ScrapedProduct,
    ScrapeError,
    ScrapeErrorCode,
    ScrapeOutcome,
    ScrapeProgress,
)

__all__ = [
    "BASE_URL",
    "ScrapeConfig",
    "ScrapeError",
    "ScrapeErrorCode",
    "ScrapeOutcome",
    "ScrapeProgress",
    "ScrapedProduct",
]
