"""One-shot coverage probe for the user-supplied 536 ETF tickers.

Reads ``data/etf_tickers_bloomberg.txt`` (Bloomberg-style
``<ROOT> <EXCHANGE>``), converts each to a Yahoo Finance symbol, then
asks yfinance for ``totalAssets`` (AUM). Reports per-exchange coverage
and a sample of misses.

Not meant to ship as a recurring tool — this is a research probe to
decide whether yfinance alone is sufficient or we need to stitch in
other sources for the misses.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

import yfinance as yf

# Bloomberg exchange suffix → Yahoo Finance suffix.
BLOOMBERG_TO_YAHOO = {
    "US": "",      # NYSE/Nasdaq — no suffix on Yahoo
    "GR": ".DE",   # Xetra
    "SW": ".SW",   # SIX Swiss
    "CN": ".TO",   # Toronto Stock Exchange
    "BZ": ".SA",   # B3 (Brazil)
    "AU": ".AX",   # ASX
    "HK": ".HK",   # HKEX
    "IT": ".MI",   # Borsa Italiana
    "NA": ".AS",   # Euronext Amsterdam
    "FP": ".PA",   # Euronext Paris
    "SS": ".ST",   # Nasdaq Stockholm
    "PW": ".WA",   # Warsaw
    "LN": ".L",    # LSE
    "NZ": ".NZ",
    "AV": ".VI",   # Vienna
    "KZ": None,    # Yahoo doesn't list Kazakhstan
}


def bloomberg_to_yahoo(bbg: str) -> str | None:
    parts = bbg.strip().split()
    if len(parts) < 2:
        return None
    root, exchange = parts[0], parts[-1]
    suffix = BLOOMBERG_TO_YAHOO.get(exchange)
    if suffix is None:
        return None
    # Canadian class shares: BTCC/B → BTCC-B on Yahoo
    root_y = root.replace("/", "-")
    # Hong Kong: pad numeric tickers to 4 digits (yfinance convention)
    if exchange == "HK" and root_y.isdigit():
        root_y = root_y.zfill(4)
    return f"{root_y}{suffix}"


def main() -> None:
    path = Path("/app/data_input/etf_tickers_bloomberg.txt")
    bbg_tickers = [
        ln.strip() for ln in path.read_text().splitlines() if ln.strip()
    ]
    print(f"Total Bloomberg tickers: {len(bbg_tickers)}")

    # Build mapping
    mapped: list[tuple[str, str | None]] = [
        (t, bloomberg_to_yahoo(t)) for t in bbg_tickers
    ]
    unmapped = [t for t, y in mapped if y is None]
    print(f"Unmappable (exchange not in conversion table): {len(unmapped)}")
    if unmapped:
        print(f"  sample: {unmapped[:5]}")

    # Probe yfinance
    print()
    print("=== Probing yfinance for totalAssets ===")
    results: list[dict] = []
    t0 = time.time()
    for i, (bbg, yahoo) in enumerate(mapped):
        if yahoo is None:
            results.append({
                "bloomberg": bbg, "yahoo": None,
                "status": "unmapped", "aum": None,
            })
            continue
        try:
            info = yf.Ticker(yahoo).info or {}
            aum = info.get("totalAssets")
            longname = info.get("longName") or info.get("shortName")
            results.append({
                "bloomberg": bbg, "yahoo": yahoo,
                "status": "ok" if aum else (
                    "no_aum" if longname else "not_found"
                ),
                "aum": aum,
                "longname": longname,
            })
        except Exception as e:
            results.append({
                "bloomberg": bbg, "yahoo": yahoo,
                "status": f"err:{type(e).__name__}",
                "aum": None,
            })
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            print(f"  {i+1}/{len(mapped)} probed, elapsed {elapsed:.1f}s")

    print()
    print("=== Coverage summary ===")
    by_status = Counter(r["status"] for r in results)
    for s, n in by_status.most_common():
        print(f"  {s:20} {n:4}  ({100*n/len(results):.1f}%)")

    print()
    print("=== Coverage by exchange ===")
    by_ex: dict[str, dict[str, int]] = {}
    for r in results:
        ex = r["bloomberg"].split()[-1]
        d = by_ex.setdefault(ex, {"ok": 0, "no_aum": 0, "not_found": 0,
                                  "unmapped": 0, "err": 0, "total": 0})
        d["total"] += 1
        if r["status"] == "ok":
            d["ok"] += 1
        elif r["status"] == "no_aum":
            d["no_aum"] += 1
        elif r["status"] == "not_found":
            d["not_found"] += 1
        elif r["status"] == "unmapped":
            d["unmapped"] += 1
        else:
            d["err"] += 1
    print(f"  {'EX':5} {'total':>6} {'AUM ok':>8} {'no AUM':>7} {'not found':>10} {'unmapped':>9} {'err':>5}  hit%")
    for ex, d in sorted(by_ex.items(), key=lambda kv: -kv[1]["total"]):
        hit_pct = 100 * d["ok"] / d["total"]
        print(f"  {ex:5} {d['total']:>6} {d['ok']:>8} {d['no_aum']:>7} {d['not_found']:>10} {d['unmapped']:>9} {d['err']:>5}  {hit_pct:.1f}%")

    print()
    print("=== Sample AUM hits ===")
    hits = [r for r in results if r["status"] == "ok"]
    print(f"  total hits: {len(hits)}")
    for r in hits[:10]:
        print(f"    {r['bloomberg']:14} → {r['yahoo']:14} AUM=${r['aum']/1e9:.2f}B  {(r.get('longname') or '')[:50]}")

    print()
    print("=== Sample misses (no_aum + not_found) ===")
    misses = [r for r in results if r["status"] in ("no_aum", "not_found")]
    for r in misses[:15]:
        print(f"    {r['bloomberg']:14} → {r['yahoo']:14} status={r['status']:10}  longname={(r.get('longname') or '')[:40]!r}")

    # Save CSV for downstream stitching analysis
    import csv
    out_path = Path("/app/data/etf_yfinance_coverage.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["bloomberg", "yahoo", "status", "aum", "longname"])
        w.writeheader()
        for r in results:
            w.writerow({
                "bloomberg": r["bloomberg"],
                "yahoo": r.get("yahoo") or "",
                "status": r["status"],
                "aum": r.get("aum") or "",
                "longname": (r.get("longname") or "").replace("\n", " ")[:120],
            })
    print(f"\nSaved {len(results)} rows to {out_path}")


if __name__ == "__main__":
    main()
