"""Agent-facing ETF tools.

``kind="etf_aum"`` lives on the yfinance Source. For card creation
the agent uses the DataRef path; for ad-hoc questions (*"what's IBIT's
AUM?"*) it calls the helpers below.

Two helpers:

- ``fetch_etf_aum(ticker)`` — single ticker, returns ``(df, source_used)``.
- ``etf_aum_scorecard(tickers)`` — many tickers, returns a sorted
  scorecard DataFrame for a TableCard / chat readout.

Both accept Bloomberg-style (``IBIT US``, ``BITC SW``) and raw Yahoo
symbols (``IBIT``, ``BITC.SW``). Conversion is documented in
``quant_radar/sources/etf_aum_src.BLOOMBERG_TO_YAHOO_SUFFIX``.

Honest coverage (probed 2026-05-28 across 536 crypto ETF tickers):
- US listings: ~83% by count, ~93% by USD AUM
- Swiss (SW): ~69% by count
- Canada (CN): ~29% by count
- European ETPs / ETCs (GR / BZ): yfinance knows the ticker but the
  AUM field is null because they aren't structured as ETFs in
  yfinance's metadata. Issuer-website scrapes would be the
  Tier-2 stitch for those.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from quant_radar.sources.etf_aum_src import (
    BLOOMBERG_TO_YAHOO_SUFFIX,
    bloomberg_to_yahoo,
    fetch_etf_aum_batch,
    fetch_etf_aum_single,
)


def fetch_etf_aum(
    ticker: str, *, refresh: bool = False,
) -> tuple[pd.DataFrame, str]:
    """AUM snapshot for one ETF ticker.

    Returns ``(df, source_used)`` mirroring the other ``fetch_*`` tools.
    ``df`` has one row indexed by fetch timestamp; columns include
    ``bloomberg / yahoo / longname / aum / nav / category / currency /
    status``. ``status`` is one of:

    - ``ok``: yfinance returned a non-null ``totalAssets``
    - ``no_aum``: yfinance knows the ticker (longname populated) but
      ``totalAssets`` is null — common for European ETPs / ETCs
    - ``not_found``: yfinance has no record of this symbol
    - ``unmapped``: the Bloomberg exchange suffix isn't in our
      conversion table (e.g. Kazakhstan)
    """
    df = fetch_etf_aum_single(ticker, refresh=refresh)
    return df, "yfinance"


def etf_aum_scorecard(
    tickers: list[str], *, refresh: bool = False,
) -> pd.DataFrame:
    """Batched scorecard — one row per ticker, sorted by AUM descending.

    Indexed by the input ticker (Bloomberg or Yahoo, whatever the user
    passed). NaN AUMs sorted last. Useful as the agent's "rank these N
    ETFs by size" output, either rendered as a TableCard or summarized
    in chat.
    """
    return fetch_etf_aum_batch(tickers, refresh=refresh)


def describe_etf_aum_coverage() -> dict[str, Any]:
    """Return the Bloomberg-exchange → Yahoo-suffix table.

    The agent reads this once to learn which Bloomberg-style tickers
    can be resolved to Yahoo. Exchanges mapped to ``None`` (e.g.
    Kazakhstan) are documented gaps.
    """
    return {
        "bloomberg_to_yahoo_suffix": dict(BLOOMBERG_TO_YAHOO_SUFFIX),
        "supported_exchanges": [
            e for e, s in BLOOMBERG_TO_YAHOO_SUFFIX.items() if s is not None
        ],
        "unmapped_exchanges": [
            e for e, s in BLOOMBERG_TO_YAHOO_SUFFIX.items() if s is None
        ],
        "notes": (
            "yfinance Ticker.info.totalAssets is the underlying field. "
            "Populated cleanly for US-listed ETFs; null for many "
            "European ETPs/ETCs (the ticker resolves, status='no_aum'). "
            "Hit rate by ticker count is ~44% across crypto ETFs but "
            "~80-90% by USD AUM — US Bitcoin spot ETFs dominate."
        ),
    }


def convert_bloomberg_to_yahoo(bloomberg: str) -> str | None:
    """Expose the Bloomberg → Yahoo conversion as an agent tool too.

    Useful when the agent needs the Yahoo symbol for an OHLCV chart
    card after looking up the AUM. Returns ``None`` if the exchange
    isn't in our conversion table.
    """
    return bloomberg_to_yahoo(bloomberg)
