"""Unit tests for sliding-window in-memory rate limiter."""

from datetime import UTC, datetime, timedelta

from app.core.clock import FrozenClock
from app.core.rate_limit import InMemoryRateLimiter


def test_rate_limiter_allows_requests_within_limit() -> None:
    """Requests under limit should be permitted."""
    clock = FrozenClock(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
    limiter = InMemoryRateLimiter(clock=clock)

    for _ in range(5):
        allowed, retry_after = limiter.check_rate_limit(
            key="test_client", limit=5, window_seconds=60
        )
        assert allowed is True
        assert retry_after == 0


def test_rate_limiter_blocks_and_returns_retry_after() -> None:
    """Exceeding limit must block and calculate retry_after."""
    clock = FrozenClock(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
    limiter = InMemoryRateLimiter(clock=clock)

    for _ in range(3):
        allowed, _ = limiter.check_rate_limit(key="test_client", limit=3, window_seconds=60)
        assert allowed is True

    # 4th request must be blocked
    allowed, retry_after = limiter.check_rate_limit(key="test_client", limit=3, window_seconds=60)
    assert allowed is False
    assert retry_after > 0
    assert retry_after <= 60


def test_rate_limiter_resets_after_window_expires() -> None:
    """After sliding window passes, subsequent requests should succeed."""
    start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(start)
    limiter = InMemoryRateLimiter(clock=clock)

    # Consume limit
    for _ in range(3):
        limiter.check_rate_limit(key="client_a", limit=3, window_seconds=60)

    # Check blocked
    allowed, _ = limiter.check_rate_limit(key="client_a", limit=3, window_seconds=60)
    assert allowed is False

    # Advance clock past window
    clock.advance(timedelta(seconds=65))
    allowed, retry_after = limiter.check_rate_limit(key="client_a", limit=3, window_seconds=60)
    assert allowed is True
    assert retry_after == 0
