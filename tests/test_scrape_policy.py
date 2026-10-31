from datetime import UTC, datetime, timedelta

from arcelikSalesHelper.infrastructure.scrape_policy import (
    GateReason,
    attempts_in_window,
    cooldown_remaining,
    is_scrape_allowed,
    is_suspicious_drop,
    quota_reached,
)

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def test_cooldown_boundaries():
    assert cooldown_remaining(None, NOW) is None
    assert cooldown_remaining(NOW - DAY, NOW) is None
    assert cooldown_remaining(NOW - DAY + timedelta(seconds=1), NOW) == (
        timedelta(seconds=1)
    )
    assert cooldown_remaining(NOW - DAY - timedelta(seconds=1), NOW) is None


def test_future_last_attempt_blocks_for_full_interval():
    assert cooldown_remaining(NOW + DAY, NOW) == DAY


def test_quota_rolling_window():
    four = [NOW - timedelta(days=d) for d in (2, 5, 9, 20)]
    assert not quota_reached(four, NOW)
    five = [*four, NOW - timedelta(days=29)]
    assert quota_reached(five, NOW)
    # the oldest falls out of the window at exactly 30 days
    later = NOW + timedelta(days=1)
    assert len(attempts_in_window(five, later)) == 4
    assert not quota_reached(five, later)


def test_gate_reports_longer_restriction_and_retry_time():
    attempts = [NOW - timedelta(days=d) for d in (2, 5, 9, 20, 29)]
    gate = is_scrape_allowed(attempts[0], attempts, NOW)
    assert gate.reason is GateReason.QUOTA
    assert gate.retry_at == attempts[-1] + timedelta(days=30)
    assert gate.used == 5

    fresh = is_scrape_allowed(NOW - timedelta(hours=1), [NOW], NOW)
    assert fresh.reason is GateReason.COOLDOWN
    assert fresh.remaining == timedelta(hours=23)


def test_gate_open():
    gate = is_scrape_allowed(None, [], NOW)
    assert gate.allowed and gate.used == 0


def test_suspicious_drop_boundary():
    assert not is_suspicious_drop(100, None)
    assert not is_suspicious_drop(50, 100)  # exactly 50 % is fine
    assert is_suspicious_drop(49, 100)
