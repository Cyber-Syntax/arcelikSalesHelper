"""Runs the crawler off the GUI thread."""

from __future__ import annotations

import asyncio
import logging
import threading

from PySide6.QtCore import QThread, Signal

from arcelikSalesHelper import strings as T
from arcelikSalesHelper.infrastructure.scrapper.models import ScrapeConfig

log = logging.getLogger(__name__)


class ScrapeWorker(QThread):
    progress = Signal(object)  # ScrapeProgress
    finished_outcome = Signal(
        object
    )  # ScrapeOutcome (QThread owns "finished")
    failed = Signal(str)

    def __init__(
        self, config: ScrapeConfig | None = None, parent: object = None
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._config = config
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            # Imported here so a missing native library cannot stop the app.
            from arcelikSalesHelper.infrastructure.scrapper import crawler

            outcome = asyncio.run(
                crawler.crawl(self._config, self.progress.emit, self._cancel)
            )
        except ImportError:
            log.exception("scraper dependencies missing")
            self.failed.emit(T.UPDATE_SCRAPER_MISSING)
        except Exception as exc:
            log.exception("scrape crashed")
            self.failed.emit(T.update_unexpected(str(exc)))
        else:
            self.finished_outcome.emit(outcome)
