"""Injectable clock protocol and implementations for deterministic time handling."""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Protocol for fetching the current time."""

    def now(self) -> datetime:
        """Return current datetime in UTC timezone."""
        ...


class SystemClock:
    """Real clock returning current system UTC datetime."""

    def now(self) -> datetime:
        """Return current system UTC datetime."""
        return datetime.now(UTC)


class FrozenClock:
    """Controllable clock for deterministic testing."""

    def __init__(self, current_time: datetime | None = None) -> None:
        self._current_time = current_time or datetime.now(UTC)
        if self._current_time.tzinfo is None:
            self._current_time = self._current_time.replace(tzinfo=UTC)

    def now(self) -> datetime:
        """Return the current frozen time."""
        return self._current_time

    def set_time(self, new_time: datetime) -> None:
        """Set the clock to a specific datetime."""
        if new_time.tzinfo is None:
            new_time = new_time.replace(tzinfo=UTC)
        self._current_time = new_time

    def advance(self, delta: timedelta) -> None:
        """Advance the clock by a timedelta."""
        self._current_time += delta


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Ensure a datetime is timezone-aware in UTC (normalizes naive SQLite datetimes)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
