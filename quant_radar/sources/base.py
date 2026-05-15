"""Common types and TTL constants for source adapters.

Every source adapter exposes one or more module-level functions that
return ``pandas.DataFrame`` with a ``DatetimeIndex`` named ``timestamp``.
The cache layer handles persistence; sources are responsible only for
fetching and shaping.
"""

from __future__ import annotations

from typing import Final

TTL_INTRADAY_SEC: Final[int] = 5 * 60
TTL_DAILY_SEC: Final[int] = 24 * 60 * 60
TTL_MACRO_SEC: Final[int] = 7 * 24 * 60 * 60


def ttl_for_interval(interval: str) -> int:
    if interval in {"1m", "5m", "15m", "1h"}:
        return TTL_INTRADAY_SEC
    return TTL_DAILY_SEC
