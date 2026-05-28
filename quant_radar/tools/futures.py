"""Agent-facing CME futures tools.

Wraps the multi-contract aggregation in
``quant_radar/sources/cme_futures_src.py`` so the agent can ask
questions like *"what's BTC's total CME futures volume over the past
month?"* or *"compare ETH vs SOL aggregate futures volume this week"*
without needing to enumerate contract months by hand.

Two tools:

- ``fetch_cme_futures_volume(asset, start, end)`` — single asset,
  returns a daily DataFrame summed across every active CME contract
  month plus the standard/micro split.

- ``cme_futures_scorecard(assets=None)`` — last available day across
  every asset in one row each, suitable for a TableCard "scorecard"
  view.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from quant_radar.cards.spec import DataRef
from quant_radar.sources.cme_futures_src import (
    ASSET_REGISTRY,
    describe_asset,
    list_all_assets,
)
from quant_radar.sources.hydrate import hydrate


def fetch_cme_futures_volume(
    asset: str, *,
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
) -> tuple[pd.DataFrame, str]:
    """Daily CME futures volume + notional aggregated across all months.

    ``asset`` accepts: BTC / ETH / SOL / XRP / LINK / ADA / XLM.
    Without ``start``/``end`` returns the last ~1 year of daily data.

    Returns ``(df, source_used)`` mirroring the other ``fetch_*`` tools.
    Columns:
        standard_contracts   (the headline "total contracts" number)
        micro_contracts      (kept separate — contract size differs)
        total_notional, standard_notional, micro_notional
        active_months_std, active_months_micro

    Notional is USD = sum(close × volume × contract_size) per day for
    each variant; ``total_notional`` is the sum of std + micro notional
    (valid because dollars are unit-consistent across contract sizes).

    There is NO ``total_contracts`` column — standard and micro CME
    contracts have different underlying sizes (e.g. BTC: 5 vs 0.1) so
    adding the counts would produce a number that means nothing in any
    unit. For a single number combining both, read ``total_notional``.
    """
    df = hydrate(
        DataRef(
            source="yfinance", kind="futures_aggregate",
            name=asset, interval="1d",
            start=start, end=end,
        ),
        refresh=refresh,
    )
    return df, "yfinance"


def cme_futures_scorecard(
    assets: list[str] | None = None, *, refresh: bool = False,
) -> pd.DataFrame:
    """Latest-day snapshot per asset — one row each.

    Returns a DataFrame indexed by asset symbol with the latest day's
    standard / micro / total contracts + notional. Useful as a single
    "where is CME volume today" TableCard.

    ``assets`` defaults to every supported asset (BTC, ETH, SOL, XRP,
    LINK, ADA, XLM). Caller can pass a subset to scope.
    """
    if assets is None:
        assets = list(ASSET_REGISTRY.keys())
    rows: list[dict[str, Any]] = []
    for asset in assets:
        try:
            df, _ = fetch_cme_futures_volume(asset, refresh=refresh)
        except Exception as e:  # noqa: BLE001
            rows.append({
                "asset": asset.upper(),
                "longname": ASSET_REGISTRY.get(asset.upper(), {}).get("longname", ""),
                "error": f"{type(e).__name__}: {str(e)[:80]}",
            })
            continue
        if df.empty:
            rows.append({
                "asset": asset.upper(),
                "longname": ASSET_REGISTRY.get(asset.upper(), {}).get("longname", ""),
                "as_of": None,
                "standard_contracts": 0,
                "micro_contracts": 0,
                "total_notional": 0.0,
            })
            continue
        last = df.iloc[-1]
        rows.append({
            "asset": asset.upper(),
            "longname": ASSET_REGISTRY[asset.upper()]["longname"],
            "as_of": df.index[-1].strftime("%Y-%m-%d"),
            "standard_contracts": int(last.get("standard_contracts", 0)),
            "micro_contracts": int(last.get("micro_contracts", 0)),
            "total_notional": float(last.get("total_notional", 0.0)),
            "standard_notional": float(last.get("standard_notional", 0.0)),
            "micro_notional": float(last.get("micro_notional", 0.0)),
        })
    out = pd.DataFrame(rows)
    # Sort by total_notional (USD-comparable across variants) for the
    # default scorecard ranking — not by contract count since those are
    # not comparable across the variant split.
    if "total_notional" in out.columns:
        out = out.sort_values("total_notional", ascending=False)
    return out.set_index("asset") if "asset" in out.columns else out


def describe_cme_futures_assets() -> list[dict[str, Any]]:
    """List every supported asset with its registry record (roots,
    contract sizes, longname).

    Useful at session start so the agent knows which assets it can
    request and what contract sizes will be used for notional math.
    """
    return [
        {**(describe_asset(a) or {}), "longname": s["longname"]}
        for a, s in ASSET_REGISTRY.items()
    ]
