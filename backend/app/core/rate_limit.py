"""Sliding-window in-memory rate limiter."""

from collections import defaultdict, deque
from datetime import timedelta
from threading import Lock

from app.core.clock import Clock, SystemClock


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter."""

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock: Clock = clock or SystemClock()
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check_rate_limit(
        self, key: str, limit: int, window_seconds: int
    ) -> tuple[bool, int]:
        """Check if request for key is permitted under limit within window_seconds.

        Returns:
            (allowed: bool, retry_after: int)
        """
        now = self.clock.now().timestamp()
        window_start = now - window_seconds

        with self._lock:
            timestamps = self._requests[key]

            # Prune timestamps outside current window
            while timestamps and timestamps[0] <= window_start:
                timestamps.popleft()

            if len(timestamps) >= limit:
                # Oldest timestamp + window_seconds gives the earliest time next request is allowed
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + window_seconds - now))
                return False, retry_after

            # Record this request
            timestamps.append(now)
            return True, 0

    def reset(self) -> None:
        """Clear all rate limit tracking."""
        with self._lock:
            self._requests.clear()
