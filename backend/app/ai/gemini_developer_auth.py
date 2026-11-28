"""Credential validation shared by Gemini Developer API adapters."""

import re
from collections.abc import Callable


def developer_api_key(read_key: Callable[[], str]) -> str:
    try:
        key = read_key()
        if re.fullmatch(r"(?:AIza[A-Za-z0-9_-]{35}|AQ\.[A-Za-z0-9_-]{17,253})", key):
            return key
    except Exception:
        pass
    raise ValueError("Gemini Developer API authentication is unavailable") from None
