"""Unit tests for injectable Clock protocol."""

from datetime import UTC, datetime, timedelta

from app.core.clock import FrozenClock, SystemClock


def test_system_clock_returns_utc() -> None:
    """SystemClock must return timezone-aware UTC datetime."""
    clock = SystemClock()
    now = clock.now()
    assert now.tzinfo == UTC
    diff = abs((datetime.now(UTC) - now).total_seconds())
    assert diff < 2.0


def test_frozen_clock_and_advance() -> None:
    """FrozenClock provides deterministic time and allows advancing."""
    fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(fixed)
    assert clock.now() == fixed

    clock.advance(timedelta(days=7))
    assert clock.now() == fixed + timedelta(days=7)
