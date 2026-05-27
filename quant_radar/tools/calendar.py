"""Agent-facing calendar tools.

Implements the multi-source routing described in
``quant_radar/sources/kind_coverage.py`` for ``kind="economic_calendar"``.

Why this module exists separately from the DataRef / card path:

The card flow assumes the agent is creating a tile for the user to
look at. Many calendar questions don't need that — *"is there a Fed
decision this week?"* should be answerable in chat without making a
card. ``fetch_economic_calendar(country)`` returns the same DataFrame
the card path would build, so the agent can read it conversationally.

The tool follows the same shape as ``fetch_sentiment``:
``(df, source_used)``. Today the chain has only one provider
(`tradingeconomics`), but the call signature is forward-compatible
for fallbacks later.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from quant_radar.cards.spec import DataRef
from quant_radar.sources import kind_coverage
from quant_radar.sources.hydrate import hydrate


def fetch_economic_calendar(
    country: str = "united-states", *,
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
) -> tuple[pd.DataFrame, str]:
    """Fetch the economic calendar for ``country`` (current week by default).

    ``country`` accepts loose forms: ``us`` / ``usa`` / ``united-states``,
    ``eu`` / ``ea`` / ``euro-area``, ``uk`` / ``gb`` / ``united-kingdom``,
    ``de`` / ``germany``, etc. (see ``tradingeconomics_src._country_slug``
    for the alias table).

    Without ``start`` / ``end``, returns the current calendar week
    (Mon 00:00 UTC → Sun 23:59 UTC). With them, filters the parsed page
    to the requested window — still bounded by the ~4 weeks Trading
    Economics renders.

    Returns ``(df, source_used)`` mirroring ``fetch_sentiment``'s shape.
    The DataFrame columns are: country, event, period, actual, previous,
    consensus, forecast — indexed by event datetime (tz-aware UTC).
    """
    cov = kind_coverage.get_coverage("economic_calendar")
    chain: list[str] = (cov or {}).get("default_chain") or ["tradingeconomics"]

    last_err: Exception | None = None
    for src in chain:
        try:
            df = hydrate(
                DataRef(
                    source=src, kind="economic_calendar",
                    name=country, interval="event",
                    start=start, end=end,
                ),
                refresh=refresh,
            )
            return df, src
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue

    raise RuntimeError(
        f"All economic_calendar providers in {chain} failed for "
        f"{country!r}. Last error: {type(last_err).__name__}: {last_err}"
    )


def describe_economic_calendar_routing() -> dict[str, Any]:
    """Return the kind_coverage record for ``economic_calendar``.

    Agent should call this once to learn which provider(s) serve
    economic calendars, the default chain, rate-limit / ToS notes, and
    coverage caveats.
    """
    cov = kind_coverage.get_coverage("economic_calendar")
    return cov or {}
