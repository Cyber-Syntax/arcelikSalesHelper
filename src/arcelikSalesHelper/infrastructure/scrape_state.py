"""Reads/writes the scrape bookkeeping keys in ``app_metadata``."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from .database import transaction
from .scrape_policy import SCRAPE_QUOTA_WINDOW, ScrapeGate, is_scrape_allowed

_K_ATTEMPT = "last_scrape_attempt_at"
_K_SUCCESS = "last_scrape_success_at"
_K_ATTEMPTS = "scrape_attempts"
_K_COUNT = "last_scrape_product_count"
_K_CHANGES = "last_scrape_change_count"
_KEYS = (_K_ATTEMPT, _K_SUCCESS, _K_ATTEMPTS, _K_COUNT, _K_CHANGES)
_ISO = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class ScrapeState:
    last_attempt: datetime | None
    last_success: datetime | None
    attempts: tuple[datetime, ...]
    product_count: int | None
    change_count: int | None


def _fmt(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(_ISO)


def _parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, _ISO).replace(tzinfo=UTC)
    except ValueError:
        return None


def _parse_int(text: str | None) -> int | None:
    try:
        return None if text is None else int(text)
    except ValueError:
        return None


def _parse_attempts(text: str | None) -> tuple[datetime, ...]:
    try:
        raw = json.loads(text or "[]")
    except ValueError:
        return ()
    if not isinstance(raw, list):
        return ()
    parsed = (_parse_time(x) for x in raw if isinstance(x, str))
    return tuple(t for t in parsed if t is not None)


def _set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_metadata (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def load_state(conn: sqlite3.Connection) -> ScrapeState:
    marks = ",".join("?" * len(_KEYS))
    rows = conn.execute(
        f"SELECT key, value FROM app_metadata WHERE key IN ({marks})", _KEYS
    )
    values = {r["key"]: r["value"] for r in rows}
    return ScrapeState(
        _parse_time(values.get(_K_ATTEMPT)),
        _parse_time(values.get(_K_SUCCESS)),
        _parse_attempts(values.get(_K_ATTEMPTS)),
        _parse_int(values.get(_K_COUNT)),
        _parse_int(values.get(_K_CHANGES)),
    )


def current_gate(conn: sqlite3.Connection, now: datetime) -> ScrapeGate:
    """Read-only gate for the intro page."""
    state = load_state(conn)
    return is_scrape_allowed(state.last_attempt, state.attempts, now)


def try_begin_attempt(conn: sqlite3.Connection, now: datetime) -> ScrapeGate:
    """Check the gate and, if open, record the attempt atomically.

    The attempt is written before the crawl starts, so failed and cancelled
    runs count toward the cooldown and the quota.
    """
    with transaction(conn):
        state = load_state(conn)
        gate = is_scrape_allowed(state.last_attempt, state.attempts, now)
        if gate.allowed:
            kept = [t for t in state.attempts if t > now - SCRAPE_QUOTA_WINDOW]
            kept.append(now)
            _set(conn, _K_ATTEMPT, _fmt(now))
            _set(conn, _K_ATTEMPTS, json.dumps([_fmt(t) for t in kept]))
    return gate


def record_crawl_success(
    conn: sqlite3.Connection,
    now: datetime,
    product_count: int,
    *,
    complete: bool,
) -> None:
    """The baseline for the drop guard only moves after a complete crawl."""
    with transaction(conn):
        _set(conn, _K_SUCCESS, _fmt(now))
        if complete:
            _set(conn, _K_COUNT, str(product_count))


def record_applied(conn: sqlite3.Connection, change_count: int) -> None:
    with transaction(conn):
        _set(conn, _K_CHANGES, str(change_count))
