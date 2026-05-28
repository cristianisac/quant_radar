"""CME crypto futures — aggregate volume across all listed contract months.

Background: yfinance exposes individual CME futures contracts as
``<ROOT><MONTH-CODE><YEAR>.CME`` (e.g. ``BTCM26.CME`` = BTC Jun 2026).
The continuous ``<ROOT>=F`` ticker is a stitched front-month series —
useful for prices but its volume is the front-month's volume only, not
the asset's total CME futures volume.

This adapter enumerates every active contract month per asset, pulls
each contract's history, and sums volume per day. Returned columns
distinguish standard vs micro because the two products serve different
participants (institutional vs retail/small-size) and combining them
silently would lose signal.

CME crypto products live on yfinance under these root pairs:

    BTC / MBT    ETH / MET    SOL / MSL    XRP / -      (MXR delisted)
    LNK / MLN    ADA / -      XLM / MXL

The ``ASSET_REGISTRY`` below records the canonical pairing plus
contract-size multipliers (units of the underlying per contract) so a
caller asking for notional USD gets a consistent answer.

Returned DataFrame (``kind="futures_aggregate"``):

    index   timestamp (tz-aware UTC, daily)
    columns
        standard_contracts   sum of vol on standard CME contracts that day
        micro_contracts      sum of vol on micro CME contracts that day
        total_contracts      standard + micro
        standard_notional    sum(close * vol * std_size) USD
        micro_notional       sum(close * vol * micro_size) USD
        total_notional       standard + micro notional
        active_months_std    count of standard contract months that traded
        active_months_micro  count of micro contract months that traded
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from quant_radar.cache import CacheKey, get_or_fetch
from quant_radar.sources.base import TTL_DAILY_SEC

SOURCE = "yfinance"  # piggybacks on yfinance for the underlying contracts

# Per-asset registry: standard + micro root tickers plus CME contract sizes
# (units of the underlying per contract). Sizes from CME contract specs.
# Set ``None`` for products that don't exist (verified by live probe
# 2026-05-28 — MXR and MAD return 404 on yfinance).
ASSET_REGISTRY: dict[str, dict[str, Any]] = {
    "BTC": {
        "standard": {"root": "BTC", "contract_size": 5.0},
        "micro":    {"root": "MBT", "contract_size": 0.1},
        "longname": "Bitcoin",
    },
    "ETH": {
        "standard": {"root": "ETH", "contract_size": 50.0},
        "micro":    {"root": "MET", "contract_size": 0.1},
        "longname": "Ether",
    },
    "SOL": {
        "standard": {"root": "SOL", "contract_size": 500.0},
        "micro":    {"root": "MSL", "contract_size": 25.0},
        "longname": "Solana",
    },
    "XRP": {
        "standard": {"root": "XRP", "contract_size": 50_000.0},
        "micro":    None,  # MXR delisted on yfinance
        "longname": "XRP",
    },
    "LINK": {
        "standard": {"root": "LNK", "contract_size": 100.0},
        "micro":    {"root": "MLN", "contract_size": 25.0},
        "longname": "Chainlink",
    },
    "ADA": {
        "standard": {"root": "ADA", "contract_size": 10_000.0},
        "micro":    None,  # MAD not on yfinance
        "longname": "Cardano",
    },
    "XLM": {
        "standard": {"root": "XLM", "contract_size": 10_000.0},
        "micro":    {"root": "MXL", "contract_size": 2_500.0},
        "longname": "Stellar",
    },
}

# CME month codes
_MONTH_CODES = ("F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z")


def _candidate_contract_months(
    root: str, *, look_back_months: int = 6, look_forward_months: int = 24,
) -> list[str]:
    """Enumerate likely-active contract month symbols for ``root``.

    Walks ``look_back_months`` months in the past (for historical
    volume) and ``look_forward_months`` months forward (for current
    open interest in back-month contracts).
    """
    out: list[str] = []
    today = datetime.now(UTC)
    # Walk months from start_year/start_month onward
    for i in range(-look_back_months, look_forward_months + 1):
        # Build year-month i months from today
        y = today.year
        m = today.month + i
        while m > 12:
            m -= 12
            y += 1
        while m < 1:
            m += 12
            y -= 1
        code = _MONTH_CODES[m - 1]
        yr2 = f"{y % 100:02d}"
        out.append(f"{root}{code}{yr2}.CME")
    return out


def _fetch_contract_history(
    symbol: str, *,
    start: datetime | None, end: datetime | None,
) -> pd.DataFrame:
    """Pull yfinance history for one CME contract. Empty on failure."""
    try:
        if start is not None and end is not None:
            h = yf.Ticker(symbol).history(
                start=start.date().isoformat(),
                end=(end + timedelta(days=1)).date().isoformat(),
                auto_adjust=False,
            )
        else:
            # Default to a year of history when no window — gives enough
            # data for plotting trends and aggregate scorecards.
            h = yf.Ticker(symbol).history(period="1y", auto_adjust=False)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    if h is None or h.empty:
        return pd.DataFrame()
    # yfinance returns naive index; localize to UTC.
    h.index = pd.to_datetime(h.index, utc=True)
    h.index.name = "timestamp"
    return h


def _aggregate_one_kind(
    root: str, contract_size: float, *,
    start: datetime | None, end: datetime | None,
) -> pd.DataFrame:
    """Sum daily volume + notional across all listed months for one root.

    Returned DataFrame columns: ``contracts``, ``notional``,
    ``active_months``. Indexed by date.
    """
    per_day: dict[pd.Timestamp, dict[str, float]] = {}
    for sym in _candidate_contract_months(root):
        h = _fetch_contract_history(sym, start=start, end=end)
        if h.empty:
            continue
        for ts, row in h.iterrows():
            vol = float(row.get("Volume") or 0)
            close = float(row.get("Close") or 0)
            if vol <= 0:
                continue
            slot = per_day.setdefault(ts, {"contracts": 0.0, "notional": 0.0, "active": 0})
            slot["contracts"] += vol
            slot["notional"] += vol * close * contract_size
            slot["active"] += 1

    if not per_day:
        return pd.DataFrame(columns=["contracts", "notional", "active_months"])
    out = pd.DataFrame(
        [
            {"timestamp": ts, "contracts": int(v["contracts"]),
             "notional": v["notional"], "active_months": v["active"]}
            for ts, v in per_day.items()
        ]
    ).set_index("timestamp").sort_index()
    out.index.name = "timestamp"
    return out


def fetch_cme_futures_volume(
    asset: str, *,
    start: datetime | None = None, end: datetime | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Aggregate daily CME futures volume for ``asset``.

    Returns a DataFrame indexed by date with columns for standard and
    micro variants separately, plus combined totals and notional USD.
    """
    asset_u = asset.upper().strip()
    if asset_u not in ASSET_REGISTRY:
        raise ValueError(
            f"unknown asset {asset!r}; supported: {list(ASSET_REGISTRY)}"
        )

    key = CacheKey(
        source=SOURCE, kind="futures_aggregate",
        name=asset_u, interval="1d",
    )

    def fetcher(
        start: datetime | None = None, end: datetime | None = None,
    ) -> pd.DataFrame:
        spec = ASSET_REGISTRY[asset_u]
        std = spec["standard"]
        mic = spec["micro"]

        std_df = _aggregate_one_kind(
            std["root"], std["contract_size"], start=start, end=end,
        )
        mic_df = (
            _aggregate_one_kind(
                mic["root"], mic["contract_size"], start=start, end=end,
            ) if mic is not None else pd.DataFrame()
        )

        # Align by index (date) so we can sum without losing days that
        # only one variant traded.
        std_df = std_df.rename(columns={
            "contracts": "standard_contracts",
            "notional": "standard_notional",
            "active_months": "active_months_std",
        })
        mic_df = mic_df.rename(columns={
            "contracts": "micro_contracts",
            "notional": "micro_notional",
            "active_months": "active_months_micro",
        })

        if std_df.empty and mic_df.empty:
            return pd.DataFrame(columns=SCHEMA_COLS)

        joined = std_df.join(mic_df, how="outer").fillna(0)
        joined["total_contracts"] = (
            joined.get("standard_contracts", 0) + joined.get("micro_contracts", 0)
        ).astype(int)
        joined["total_notional"] = (
            joined.get("standard_notional", 0) + joined.get("micro_notional", 0)
        )
        # Cast counts to int for cleaner serialization.
        for col in ("standard_contracts", "micro_contracts",
                    "active_months_std", "active_months_micro"):
            if col in joined.columns:
                joined[col] = joined[col].fillna(0).astype(int)

        return joined[[c for c in SCHEMA_COLS if c in joined.columns]]

    return get_or_fetch(
        key, fetcher, start=start, end=end, refresh=refresh,
        ttl_seconds=TTL_DAILY_SEC,
    )


SCHEMA_COLS = [
    "total_contracts", "standard_contracts", "micro_contracts",
    "total_notional", "standard_notional", "micro_notional",
    "active_months_std", "active_months_micro",
]


def describe_asset(name: str) -> dict[str, Any] | None:
    """Return the registry record for ``name`` (used by the yfinance
    Source's ``describe`` dispatch when kind=futures_aggregate)."""
    spec = ASSET_REGISTRY.get((name or "").upper())
    if not spec:
        return None
    return {
        "symbol": name.upper(),
        "longname": spec["longname"],
        "standard_root": spec["standard"]["root"],
        "standard_contract_size": spec["standard"]["contract_size"],
        "micro_root": spec["micro"]["root"] if spec["micro"] else None,
        "micro_contract_size": spec["micro"]["contract_size"] if spec["micro"] else None,
    }


def search_assets(query: str, *, limit: int = 20) -> list[dict]:
    q = (query or "").upper()
    hits = [
        {"symbol": a, "longname": s["longname"]}
        for a, s in ASSET_REGISTRY.items()
        if q in a or q in s["longname"].upper()
    ]
    return hits[:limit]


def list_all_assets() -> list[dict]:
    return [
        {"symbol": a, "longname": s["longname"]}
        for a, s in ASSET_REGISTRY.items()
    ]
