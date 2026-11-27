"""Read IANA rules from the pinned Python tzdata distribution on every platform."""

from functools import cache, lru_cache
from importlib.resources import files
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@cache
def _timezone_keys() -> frozenset[str]:
    return frozenset(files("tzdata").joinpath("zones").read_text(encoding="utf-8").splitlines())


@lru_cache(maxsize=256)
def load_timezone(key: str) -> ZoneInfo:
    if key not in _timezone_keys():
        raise ZoneInfoNotFoundError("Invalid IANA timezone identifier")
    resource = files("tzdata.zoneinfo").joinpath(*key.split("/"))
    try:
        with resource.open("rb") as source:
            return ZoneInfo.from_file(source, key)
    except (OSError, ValueError):
        raise ZoneInfoNotFoundError("Unknown IANA timezone identifier") from None
