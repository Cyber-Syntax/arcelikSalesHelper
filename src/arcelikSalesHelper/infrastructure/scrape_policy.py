"""Pure rate-limit policy. Every function takes an injected ``now``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

SCRAPE_MIN_INTERVAL = timedelta(hours=24)
SCRAPE_MIN_INTERVAL_ENV_VAR = "ARCELIK_SCRAPE_MIN_INTERVAL_SECONDS"
SCRAPE_QUOTA_LIMIT = 5
SCRAPE_QUOTA_WINDOW = timedelta(days=30)
SCRAPE_SUSPICIOUS_DROP_RATIO = 0.5


class GateReason(Enum):
    OK = "ok"
    COOLDOWN = "cooldown"
    QUOTA = "quota"


@dataclass(frozen=True)
class ScrapeGate:
    reason: GateReason
    retry_at: datetime | None = None
    remaining: timedelta | None = None
    used: int = 0
    limit: int = SCRAPE_QUOTA_LIMIT

    @property
    def allowed(self) -> bool:
        return self.reason is GateReason.OK


def configured_min_interval() -> timedelta:
    """Return the cooldown, optionally overridden for development runs."""
    raw = os.environ.get(SCRAPE_MIN_INTERVAL_ENV_VAR)
    if raw is None:
        return SCRAPE_MIN_INTERVAL
    try:
        seconds = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{SCRAPE_MIN_INTERVAL_ENV_VAR} must be a non-negative integer"
        ) from exc
    if seconds < 0:
        raise ValueError(
            f"{SCRAPE_MIN_INTERVAL_ENV_VAR} must be a non-negative integer"
        )
    return timedelta(seconds=seconds)


def cooldown_remaining(
    last_attempt: datetime | None,
    now: datetime,
    minimum: timedelta | None = None,
) -> timedelta | None:
    """Time left to wait, or None when a run is allowed.

    Exactly ``minimum`` elapsed is allowed. A last attempt in the future (the
    clock moved back) counts as zero elapsed time: the full wait applies.
    """
    if minimum is None:
        minimum = configured_min_interval()
    if last_attempt is None:
        return None
    elapsed = max(now - last_attempt, timedelta(0))
    return None if elapsed >= minimum else minimum - elapsed


def attempts_in_window(
    attempts: Sequence[datetime],
    now: datetime,
    window: timedelta = SCRAPE_QUOTA_WINDOW,
) -> tuple[datetime, ...]:
    """Attempts strictly newer than ``window`` (future ones still count)."""
    return tuple(sorted(t for t in attempts if t > now - window))


def quota_remaining(
    attempts: Sequence[datetime],
    now: datetime,
    limit: int = SCRAPE_QUOTA_LIMIT,
    window: timedelta = SCRAPE_QUOTA_WINDOW,
) -> timedelta | None:
    """Wait until a quota slot frees up, or None when under the limit."""
    if limit < 1:
        raise ValueError("quota limit must be at least 1")

    recent = attempts_in_window(attempts, now, window)
    if len(recent) < limit:
        return None
    return max(recent[-limit] + window - now, timedelta(0))


def quota_reached(
    attempts: Sequence[datetime],
    now: datetime,
    limit: int = SCRAPE_QUOTA_LIMIT,
    window: timedelta = SCRAPE_QUOTA_WINDOW,
) -> bool:
    return quota_remaining(attempts, now, limit, window) is not None


def is_scrape_allowed(
    last_attempt: datetime | None,
    attempts: Sequence[datetime],
    now: datetime,
    *,
    minimum: timedelta | None = None,
    limit: int = SCRAPE_QUOTA_LIMIT,
    window: timedelta = SCRAPE_QUOTA_WINDOW,
) -> ScrapeGate:
    if minimum is None:
        minimum = configured_min_interval()
    used = len(attempts_in_window(attempts, now, window))
    cooldown = cooldown_remaining(last_attempt, now, minimum)
    quota = quota_remaining(attempts, now, limit, window)
    if cooldown is None and quota is None:
        return ScrapeGate(GateReason.OK, used=used, limit=limit)
    # Report whichever restriction lasts longer.
    if quota is None or (cooldown is not None and cooldown >= quota):
        assert cooldown is not None
        return ScrapeGate(
            GateReason.COOLDOWN, now + cooldown, cooldown, used, limit
        )
    return ScrapeGate(GateReason.QUOTA, now + quota, quota, used, limit)


def is_suspicious_drop(
    current_count: int,
    baseline_count: int | None,
    ratio: float = SCRAPE_SUSPICIOUS_DROP_RATIO,
) -> bool:
    """Strictly below ``ratio`` of the last good crawl; no baseline = False."""
    if not baseline_count:
        return False
    return current_count < baseline_count * ratio
