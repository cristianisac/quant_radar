---
name: quant-radar
description: AI-native market research dashboard. Use these tools to fetch market/macro/news data, run technical analysis, and create cards on the user's main or working dashboard. The user talks to you; you call tools and persist cards. Cards live on disk; a separate Streamlit viewer reads them.
---

# Quant Radar — agent contract

This file is the manifest for Claude Code sessions working on or with `quant_radar`. Read it on every turn that involves the project.

## Parallel tool calls — fan out independent work

When the user requests multiple cards that don't depend on each other —
e.g. *"give me a BTC chart with RSI, a top-10 ETF AUM table, and a
3-month unemployment chart"* — **issue the `create_dashboard_card` (and
underlying fetch) calls in parallel**, not sequentially. Anthropic's API
supports multiple tool uses per turn, and each card hits a different
upstream API anyway, so serializing them is pure latency waste.

Rule of thumb:

- **Independent cards** (different tickers / sources / kinds) → parallel.
  All three appear on the dashboard within seconds, not one-by-one.
- **Sequential cards** (e.g. "compute X, then create a card from the
  result") → serial, because the second call depends on the first.
- **Card + analysis** (e.g. "make the chart and tell me the regime") →
  parallel for the data fetch + chart creation, serial for the analysis
  step that reads the resulting frame.

When in doubt, look for *data dependency*. If card B doesn't need card
A's output, run them in parallel.

## Coverage discipline — only use the documented infrastructure

This is the **strictest rule** in this project. Read it at session
start and re-read before every card creation.

**Cards may only be created using ``quant_radar.tools.*`` + the
(source, kind) pairs documented in ``TOOLS.md``.** Do NOT use
``WebFetch``, ad-hoc ``Bash`` scraping, MCP shortcuts, or any other
out-of-band path to build a card. The whole point of this codebase
is the curated, auditable data surface; freelancing defeats it.

If a user request requires data or a tool NOT in ``TOOLS.md``, STOP.
Call ``tools.request_user_decision(description=...)`` and surface
its three-option menu to the user verbatim:

- **A · Exit** — abandon the request, dashboard unchanged.
- **B · Integrate** — close the app (`Ctrl+C` on `make app`), open a
  dev session, add the tool/source/kind following the new-source
  waterfall in this file, run pytest + the integration audit + a
  Playwright E2E, restart with `make app`, re-ask.
- **C · One-off in terminal** — only if you (the agent) can answer
  the question via base tools (``WebFetch``, ``Bash``, ad-hoc
  Python). Print the result in chat. **Do NOT create a card.** Cards
  are reserved for ``quant_radar.tools.*`` outputs.

Wait for the user's pick before doing anything. Don't preemptively
execute option C. Don't pretend a card is from a documented source
when it's actually scraped ad-hoc.

If you're not sure whether a request is supported, scan ``TOOLS.md``
+ the kind/source tables below before answering. Cheaper than calling
an unsupported adapter and apologizing afterward.

## What this project is

A local Python package + Streamlit viewer. The user describes what they want (a chart, an analysis, a news scan) and you call typed Python tools that:
1. Fetch data (cached on disk).
2. Compute indicators / detect patterns.
3. Produce a **card spec** (declarative JSON).
4. Write that spec to `main.db` (persistent) or `working.json` (session-scoped).

The Streamlit viewer is a passive renderer. It does not run the agent.

## Two dashboards

- **Main** — `data/cards/main.db` (SQLite). Survives across sessions. Anything saved here stays until explicitly removed.
- **Working** — `data/cards/working.json`. Per-session scratchpad. When the user asks to start a new working dashboard, overwrite this file with an empty structure — previous working cards are intentionally lost.

If a user request is ambiguous about target, default to **working**. Only write to main when the user says "save to main", "persist", or similar.

## Cache & refresh

- Default fetches read from cache; only the missing/expired delta is fetched.
- If the user says "refresh", "update", "latest", or asks for data newer than the cache, call the tool with `refresh=True`. The cache layer decides whether to append-merge or full-overwrite.
- There is no background streaming. Data is updated only on explicit user request.

## Date ranges from natural language

When the user asks for a time-bounded view ("BTC for 2022-2023", "last 6 months", "since the Fed pivot"), convert to ISO `start`/`end` and pass them through:

- `"2022-2023"` → `start="2022-01-01", end="2023-12-31"`
- `"Q4 2024"` → `start="2024-10-01", end="2024-12-31"`
- `"last 6 months"` → compute from today's date in env
- `"since 2020"` → `start="2020-01-01"` (no end)
- `"first half of 2023"` → `start="2023-01-01", end="2023-06-30"`

Where to pass them:
- **At fetch time** (preferred) — set `start`/`end` on the `DataRef` when calling `create_dashboard_card`. The adapter slices server-side, the cache stores just that window, and the chart only renders that range.
- **Post-fetch** — call `tools.filter_by_date(df, start, end)` on any DataFrame the source returns. Works regardless of source/kind because every adapter normalizes to a `DatetimeIndex`.
- **Pattern detection** — `detect_channels`, `detect_breakouts`, and `detect_patterns_vision` all accept `start`/`end` directly, so "find a channel in BTC during 2024-Q4" doesn't need a separate slicing step.

## Pattern detection UX

When the user asks for channels, patterns, or breakouts, **default to the vision path** unless they explicitly ask for the algorithmic detector or "both":

1. Call `tools.detect_patterns_vision(df, asset_name=...)` to render the chart
2. `Read` the returned `image_path` and identify patterns visually
3. Report each pattern with a confidence ∈ [0, 1]; draw only if confidence ≥ 0.7
4. If you cannot find a high-confidence pattern visually, fall back to `tools.detect_channels(df, ...)` (algorithmic) and report its `confidence`; draw only if ≥ 0.65

If the user says "both", run both paths and reconcile — prefer the visual finding unless the algorithm has materially higher confidence on a different pattern.

If neither path clears its threshold, say so plainly. Do not draw.

## Tools

_(catalog grows each phase; see `plan/PROGRESS.md` for status)_

**Available now (Phases 1–2):**

Data sources (return `pandas.DataFrame` with `DatetimeIndex` named `timestamp`):
| Tool | Purpose |
|---|---|
| `quant_radar.sources.yfinance_src.fetch_ohlcv(symbol, interval="1d", start, end, refresh)` | yfinance OHLCV — equities, ETFs, FX, indices. Defaults to 5y of daily history if `start` is omitted. |
| `quant_radar.sources.binance_src.fetch_ohlcv(symbol, interval="1d", start, end, refresh)` | **Primary crypto source.** Binance public spot API, no key, no signup. Bare symbols (`BTC`, `ETH`, `SOL`) map to `*USDT`; pre-formed pairs (`BTCUSDT`) pass through. |
| `quant_radar.sources.fred_src.fetch_macro_series(series_id, start, end, refresh)` | FRED macro (DGS10, CPIAUCSL, etc.). No API key. |

Source introspection (Phase 10):

| Tool | Purpose |
|---|---|
| `tools.list_sources()` | Return every source with its capabilities (intervals, history, coverage, auth, rate limits, status). Read this at the **start of a session** so you know which source covers what. |
| `tools.describe_source(name)` | Look up one source's capability by name. |
| `tools.probe_history(symbol, source="yfinance", kind="ohlcv")` | Hit the API and report the actual earliest/latest bar for a specific asset. Uses `refresh=True` to bypass the cache. Use it when the user asks *"how far back does this go?"* or before fetching a long series for the first time. |

### Discovery (universal contract)

Every source implements `search(query, limit)` + `describe(name)` so the agent has the same lookup affordances regardless of which API you're touching:

| Tool | Purpose |
|---|---|
| `tools.search_source(source, query, limit=20)` | Generic search dispatched by source name. Returns `[{symbol, longname, ...source-specific fields}]`. |
| `tools.describe_symbol(source, name)` | Generic per-symbol long-form metadata. Returns `None` if the symbol isn't recognized. |
| `tools.list_searchable_sources()` | Snapshot of which sources are currently registered + their status. |
| `tools.search_fred(query, limit=20)` | FRED keyword search (~800k series). Returns `id/longname/frequency/units/observation_start/popularity/notes`. Requires `FRED_API_KEY`. |
| `tools.search_yfinance(query, limit=10)` | yfinance keyword search via Yahoo. Returns `symbol/longname/exchange/quote_type/sector/industry`. **Yahoo doesn't expose a full exchange listing** — this is the only discovery path. |
| `tools.search_binance(query, limit=20)` | Binance spot-pair search. Matches "Bitcoin" or "BTC" → BTCUSDT. Long names from a canonical map (top assets) + CoinGecko fallback. |
| `tools.list_binance_pairs(quote="USDT")` | Enumerate every Binance spot pair (filterable by quote). Yes, fully enumerable — ~2000 pairs total. |

**When to reach for these** — any time the user mentions a name/keyword you don't already recognize as an exact symbol. Run search first, pick the top hit, then create the card. Don't guess at tickers.

### OpenBB MCP (live, ad-hoc fallback)

If the user asks for data from a source we don't have a native adapter for (Polygon, FMP, Tiingo, Intrinio, BLS, IMF, OECD, SEC, etc.), reach for the OpenBB MCP **before** considering a new adapter. Tools appear as `mcp__openbb__*`. The MCP exposes ~100 providers without our 311MB install:

- For one-shot queries ("what's Polygon's latest AAPL price?"), call the MCP tool directly — no card needed.
- For something the user wants on the dashboard, create a card with `type="analysis"` containing the MCP-fetched values rendered as markdown, OR write a thin `_OpenBBSource` adapter (~20 LOC) if it'll be used repeatedly.
- The MCP requires API keys for paid providers (FMP_API_KEY, TIINGO_API_KEY, POLYGON_API_KEY, etc.); fails gracefully when missing.

This is the realized "step 2" in the new-source waterfall (existing lib → OpenBB → MCP federation → hand-written). For native sources we already have (yfinance / binance / fred), keep using them — they're tighter, have custom bug fixes, and our card system flows through them cleanly.

### Other deferred opportunities
- **finnhub-python swap** — current finnhub adapter uses raw `requests` (~78 LOC). The official `finnhub-python` client would consolidate to ~50 LOC and unlock 50+ extra Finnhub endpoints (forex, fundamentals, earnings, calendar). Skipped because the test-mock refactor offsets the LOC savings; revisit when we actually want those endpoints.

### Multi-source routing for a single data type

When multiple sources serve the same ``kind`` (e.g. sentiment from
Alpha Vantage AND Marketaux, or fundamentals from FMP AND Polygon),
the agent shouldn't guess which to use. Read the structured comparison
at **``quant_radar/sources/kind_coverage.py``** — it declares per-kind:

- ``providers``: each source with tier (primary/fallback/complementary), rate limit, history depth, coverage breadth, signal-quality notes
- ``default_chain``: the routing order to walk when no source is specified
- ``routing_logic``: when to switch / combine / fall back

For sentiment specifically the routing is:

1. **Alpha Vantage** (primary) — best per-ticker scoring quality, but tight 25/day quota
2. **Marketaux** (fallback) — wider symbol coverage, 100/day quota, less rich scoring
3. **Finnhub** insider-sentiment + recommendation (complementary) — orthogonal signal, NOT a substitute for news sentiment
4. **GDELT** tone (article-level) — for general mood, NOT per-ticker

The agent should call ``tools.fetch_sentiment(ticker)`` which walks
the chain automatically; the call returns ``(df, source_used)`` so the
UI/agent can show which provider served the data. ``tools.describe_sentiment_routing()``
returns the full comparison record when the user asks why a particular
source was used.

For **social_sentiment** (separate kind — Reddit mention-velocity, not
news polarity), routing is single-source:

1. **Apewisdom** (primary) — public no-auth endpoint; covers stocks/ETFs/listed companies via `all-stocks` filter (~870 tickers) and crypto via `all-crypto` (~160 tickers). Returns a current snapshot row per ticker: mentions, mentions_24h_ago, mentions_change_pct, upvotes, rank, rank_24h_ago. Commodities/bonds only surface via listed proxies (GLD, TLT, USO). Stocktwits and Reddit-direct were deferred (Cloudflare gates / unreliable signup).

Call ``tools.fetch_social_sentiment(ticker)``. The two kinds are
**orthogonal**: a ticker can be high-mention but neutral-polarity (mixed
coverage) or low-mention but strongly positive (analyst upgrade, no
chatter yet). Combine them when the user wants the full picture.

When you add a new source for an existing kind, update ``kind_coverage.py`` AND the source's catalog entry. Both must agree on the relationship.

### Cross-kind relationships — which data types pair

Three different views of the data landscape exist; read them at session start to know what to pull:

1. **`catalog.py`** *(per-source)* — "what does Polygon serve?" Use `tools.describe_source(name)`.
2. **`kind_coverage.py`** *(cross-source for one kind)* — "Alpha Vantage AND Marketaux both serve sentiment, how do they relate?" Use `tools.describe_kind_coverage(kind)`.
3. **`kind_relationships.py`** *(cross-kind)* — "social_sentiment and sentiment are orthogonal axes; pull both." Use `tools.list_kind_relationships()` or `tools.relationships_for_kind(kind)`.

Relationship types:
- ``orthogonal``: different axes, neither replaces the other (social_sentiment ↔ sentiment)
- ``siblings``: distinct frames that compose a fuller picture (income + balance + cash)
- ``primary_plus_context``: primary signal + context (ohlcv + news, macro + ohlcv)
- ``alternative_views``: same phenomenon, different lens (algorithmic vs vision patterns)

When the user asks about a ticker, run `tools.relationships_for_kind(kind)` on the primary kind they're after — it tells you which additional cards to create alongside.

### Adding a new source — the waterfall

Don't write a 100-line adapter when an existing tool already covers it. The order below is "cheapest path that gets the job done". Stop at the first match. Note the order depends on what you need:

**If the user wants an ad-hoc one-shot answer (no card needed):**

1. **MCP** — we have `openbb-mcp-server` installed at user scope. The agent calls `mcp__openbb__*` tools directly. **Zero new code per source.** Covers all ~100 OpenBB-Platform providers (FMP, Tiingo, Polygon, Intrinio, SEC EDGAR, IMF, OECD, ...). Pick this for ad-hoc queries.
2. **Vendor-official MCP** — check [modelcontextprotocol.io/servers](https://modelcontextprotocol.io/servers). Some vendors ship their own MCP (Stripe, Linear, Sentry, Datadog). If it exists, federate via `claude mcp add` — no adapter, no Python install.
3. **Raw HTTP** — like we did for CFTC. Works inside Docker with `--env-file .env`. Acceptable for genuine one-offs; not a recurring pattern.

**If the user wants card integration / recurring use (the Source ABC matters):**

1. **OpenBB Platform provider?** `pip install openbb-<provider>` (or full `openbb` for many at once), then write a ~20-LOC `_OpenBBSource` subclass that wraps `obb.<category>.<command>(provider="...")`. Card-integrated, follows ABC, ~95% of new sources land here.
2. **Existing dedicated Python lib?** (yfinance, fredapi, python-binance, ...) Only when (a) OpenBB doesn't have the provider, or (b) the lib has features OpenBB's wrapper doesn't expose. Wrap it in a thin adapter, ~30 LOC.
3. **Hand-written adapter.** Read the API docs (LLM-assisted is normal). ~100 LOC. Last resort.

**Why MCP-first for ad-hoc, OpenBB-first for cards:**
- MCP has zero marginal cost per source but returns data to the agent ad-hoc — no flow into our `DataRef` → DataFrame → card pipeline.
- OpenBB Platform installed in our image lets a 20-LOC `_OpenBBSource` subclass feed any provider into the full system (cards, search, describe, refresh, tools_for_ref).
- Standalone Python libs were preferred when we didn't have OpenBB. Now that the OpenBB MCP is installed at user scope and the Platform is the natural fit for everything financial, they're the fallback, not the default.

Use the scaffold:
```
python scripts/scaffold_source.py <name>
```
That generates the stub adapter + catalog entry stub with TODO markers. Then fill them in and run `python scripts/integration_audit.py` — the audit fails if any contract method is missing.

**Time-series sources MUST satisfy the `Source` ABC** (4 required + 1 optional method, plus catalog `schema`):
- `supports(ref)` — gate dispatch
- `fetch(ref, refresh)` — return a `DataFrame` with `DatetimeIndex` named `timestamp` and columns matching the declared schema
- `search(query, limit)` — find candidates by keyword (return `[]` if genuinely unsupported)
- `describe(name)` — per-symbol long-form metadata (return `None` if unsupported)
- `list_all(limit)` — enumerate every symbol/series this source offers. Default returns `[]`. Only override for sources with bounded catalogs (Binance ~2k spot pairs). For FRED's ~800k series and yfinance's open universe, callers reach for `search(query)` instead.

**News sources have a different contract.** They return `list[dict]` of articles, not time-series, so they don't conform to the `Source` ABC. They live in the catalog (so the agent knows they exist) but use their own functions (`fetch_news`, `fetch_top_headlines`). If you add a new news source, follow the same waterfall but skip the ABC and write `fetch_<name>_news(query, ...) -> list[dict]`.

**Capability cheatsheet** (the catalog has the canonical text):
- **yfinance** — daily/weekly/monthly from listing date (AAPL: 1980+, TSLA: 2010-06-29 IPO, BTC-USD: 2014-09-17). Intraday only 7–730 days back depending on interval. Cache-first; rate limits are aggressive.
- **binance** — crypto OHLCV from pair listing on Binance (BTCUSDT/ETHUSDT: 2017-08-17, BNBUSDT: 2017-11-06, SOLUSDT: 2020-08-11). 1200 req-weight/min. No key. **Most reliable source.**
- **fred** — macro with native frequency per series (DGS10 daily from 1962, CPIAUCSL monthly from 1947, GDP quarterly from 1947). Don't assume daily granularity.
- **gdelt** — global news, Lucene query syntax, rolling content from 2015. Live-tested at ~83% reliability with high latency variance (7–87s). Free-tier IP rate limit bites fast. **Avoid `OR` queries** — they consistently return 0 items in our tests; prefer single terms, `AND`, or quoted phrases. Treat as opportunistic, not critical-path.
- **finnhub** — finance news; requires `FINNHUB_API_KEY` env var. **Use this when news matters** — higher rate limits + curated coverage.
- **fmp** — equity OHLCV + **forex OHLC** via OpenBB Platform's `fmp` provider. Requires `FMP_API_KEY`. Free tier: 250 req/day (tight — cache-first essential). Forex symbols use no separator (`EURUSD`, `GBPUSD`).
- **tiingo** — equity OHLCV + **forex OHLC** + IEX intraday via OpenBB Platform's `tiingo` provider. Requires `TIINGO_API_KEY`. Free tier: 1000 req/hr (generous). Forex same convention as FMP.
- **polygon** — equity OHLCV + **forex OHLC** via hand-written REST adapter (Polygon not in OpenBB's bundled providers). Requires `POLYGON_API_KEY`. Free tier: 5 calls/min + ~2 years history. Forex tickers internally prefixed `C:` by the adapter; user passes the bare pair (`EURUSD`).

### OHLCV variants — what each source covers

| Asset class | Best free source(s) | Symbol convention |
|---|---|---|
| Equities + ETFs daily | `yfinance` (broadest) / `fmp` / `tiingo` / `polygon` | Bare ticker (AAPL, SPY) |
| Equities intraday (1m/5m/1h) | `tiingo` (IEX free) / `fmp` / `polygon` / `yfinance` (limited) | Bare ticker + `interval=` |
| Crypto OHLCV daily | `binance` (preferred) / `yfinance` `*-USD` | `BTCUSDT` on binance, `BTC-USD` on yfinance |
| **Forex OHLC** | `fmp` / `tiingo` / `polygon` | `EURUSD`, `GBPUSD`, `USDJPY` (6-letter pair, no separator) |
| Futures (continuous front-month) | `yfinance` only (`*=F`) | `ES=F`, `BTC=F`, `GC=F`, `CL=F` — none of the new four providers serve futures on their free tier |
| Macro time series | `fred` only | Series ID (`DGS10`, `CPIAUCSL`) |
| Indices | `yfinance` (`^GSPC`) / `fmp` / `polygon` | Caret prefix on yfinance, bare on others |

## Adding a new data source — checklist

When adding any new API source to `quant_radar`, walk this checklist. Every item is the codified version of a bug or surprise we hit while building the existing sources — skip at your peril.

### 1. Authentication
- [ ] Free, no key → easiest path.
- [ ] Free with registration → require an env var (e.g. `FINNHUB_API_KEY`); raise a clear `RuntimeError` if missing.
- [ ] Paid only → mark `status: deferred` or `paid-only` in the catalog and route the agent away.

### 2. Sensible defaults
- [ ] If the API defaults to a short lookback when `start` is omitted, **override it** in the adapter. yfinance defaults to ~1 month → SMA_200 is impossible → every chart silently wrong. Use the same per-interval defaults pattern (`_DEFAULT_LOOKBACK`) we have in `yfinance_src` and `binance_src` (5y daily / 90d intraday).
- [ ] Map our standard intervals (`1m`, `5m`, `15m`, `1h`, `1d`, `1w`, `1mo`) to the source's native names. Raise `ValueError` for unsupported intervals.

### 3. Symbol normalization
- [ ] Define one canonical form per source. Convert user-friendly input at the adapter boundary. Binance: `BTC` → `BTCUSDT`. yfinance crypto: `BTC` → `BTC-USD`. CoinGecko: `bitcoin`. Pin this once; the agent never has to guess.
- [ ] Guard against degenerate cases — e.g. `BTC` alone matches the `BTC` quote suffix; require `len(symbol) > len(suffix)` before pass-through.

### 4. Response normalization
- [ ] Return `pandas.DataFrame` with a **UTC-aware `DatetimeIndex` named `timestamp`**.
- [ ] Lowercase column names: `open`, `high`, `low`, `close`, `volume` for OHLCV; `value` for single-series macro.
- [ ] Empty responses → return an empty DataFrame, do not raise. The cache (`_ensure_index`) tolerates them.

### 5. Caching
- [ ] Wire through `quant_radar.cache.get_or_fetch(CacheKey(source, kind, name, interval), fetcher, ttl_seconds=...)`.
- [ ] TTL via `quant_radar.sources.base.ttl_for_interval(interval)` (intraday 5min, daily 24h) or `TTL_MACRO_SEC` (7d).

### 6. Error handling
- [ ] `resp.raise_for_status()` on all HTTP calls.
- [ ] **Retry with back-off** for `429`, `5xx`, `requests.ReadTimeout`, `requests.ConnectTimeout`. Pattern: a `_RETRY_DELAYS = (1.0, 3.0)` tuple iterated with `None` as final sentinel — see `gdelt_src` for the canonical version.
- [ ] **Timeout**: 30s for free / public APIs (often slow), 15s for paid / fast ones.

### 7. Pagination (only if applicable)
- [ ] If the API caps page size (Binance: 1000 klines), paginate. Advance the cursor by `last_close_ms + 1`. Stop on short pages or no progress.
- [ ] Sleep briefly between pages (`time.sleep(0.05)`) to be polite.

### 8. Live verification (mandatory before commit)
- [ ] Run `tools.probe_history("<sample symbol>", source="<name>", kind="<ohlcv|macro|...>")` from `make docker-shell`.
- [ ] Verify earliest, latest, total bars for **at least 3 sample symbols** (don't generalize from one).
- [ ] Note the **native frequency** of the data — FRED's CPIAUCSL is monthly, GDP is quarterly. Don't assume daily.
- [ ] Confirm the response shape matches our normalization contract.
- [ ] **Minimum-history gate for OHLCV / macro sources.** At least one mainstream symbol must satisfy a 200-period equivalent at the source's native frequency:
    - daily / weekly / monthly / quarterly / annual → **≥250 / ≥52 / ≥24 / ≥8 / ≥5 bars** respectively
    - If no symbol clears the bar, the source still ships — but mark it `status: "limited"` in the catalog (instead of `active`) and document the cap in `notes`. The agent will then **not** reach for it for trend analysis or moving averages, but may still use it for current-value queries.

### 9. Catalog entry (required)
- [ ] Add a `SourceCapability` to `quant_radar/sources/catalog.py` with the verified history depths, intervals, coverage, auth, rate-limit, status, and example symbols.
- [ ] Set `status` to `active`, `deferred`, or `paid-only`. `notes` for any caveat.

### 10. UI plumbing
- [ ] Teach `quant_radar/ui/data.py:hydrate` how to route a `DataRef(source="<new>")` to the new adapter. Without this the viewer can't render cards from your source.

### 11. Tests
- [ ] **Mock HTTP** with `responses` — never hit the live API in pytest.
- [ ] Cover at minimum: cold call, warm-cache hit, `refresh=True`, error propagation, pagination (if applicable), unsupported interval, missing auth (if applicable).
- [ ] Optional `@pytest.mark.network` test for a live smoke (skipped by default; the project's `addopts` filter excludes them).

### 12. SKILL.md update
- [ ] Add the new source to the data-sources table and the capability cheatsheet above.

### Common pitfalls (already burned us — don't repeat)

- **Default lookback ≠ enough bars for indicators.** Adapter must override when the API's default is short. *(Bug A, Phase 9 — yfinance.)*
- **Tz-naive timestamps from the API + tz-aware slice bounds = crash.** Always normalize via `_ensure_index`. *(Phase 10 fix.)*
- **Empty responses are real.** Cache and `_ensure_index` must tolerate zero-row frames. *(Phase 10 fix.)*
- **Native frequency != requested interval.** FRED daily/monthly/quarterly series exist side by side — querying `interval="1d"` doesn't promote a monthly series. Document in the catalog. *(FRED lesson.)*
- **Free-tier rate limits hit fast.** Retry-on-429 + on-timeout is mandatory, not optional. *(GDELT lesson.)*
- **Free APIs change pricing.** CoinPaprika moved historical OHLCV behind a paid plan mid-2025. Keep adapters lean so a swap to the next free thing (we chose Binance) is days, not weeks.
- **Symbol normalization is a one-shot fight.** Pick the canonical form per source up front; never let the agent guess.
- **Live behavior ≠ test behavior.** Mocked tests can't catch default-lookback bugs, tz-naive bugs, or rate limiting. **Always run the live probe + E2E in Docker before committing a new source.**

Cache TTL: 5min intraday / 24h daily / 7d macro. Within TTL the cache is authoritative — only `refresh=True` or expired TTL triggers a real fetch.

Analytics (importable as `from quant_radar import tools`):
| Tool | Returns |
|---|---|
| `tools.compute_returns(df, periods=("1d","1w","1m","1y","yoy","ytd"))` | `dict[str, float \| None]` |
| `tools.compute_indicators(df, which=("sma_50","sma_200","rsi","atr","macd"))` | enriched DataFrame. **SMA/EMA/RSI/ATR are parametric**: `sma_<N>`, `ema_<N>`, `rsi[_<N>]`, `atr[_<N>]` for any N≥2. Request `sma_137` or `ema_42` — no code edit needed, both the Python tool and the chart overlay renderer parse the period from the key. |
| `tools.analyze_moving_averages(df, fast_period=50, slow_period=200, asset="X")` | dict with above/below 50d/200d, 50d-vs-200d, catching-up-from-below, golden/death cross, summary |
| `tools.analyze_indicators(df)` | `{"rsi_state": ..., "volatility_regime": ... or None}`. `volatility_regime` is `None` on non-OHLCV frames (no ATR possible). |
| `tools.rolling_zscore(df, column=None, window=30, min_obs=30)` | enriched DataFrame with a `zscore_{window}` column. Trailing-window (x - mean) / std. `min_obs` defaults to 30 to guard against thin samples. |

**Analytical tools are column-agnostic.** All of them auto-pick a price column with priority `close` → `value` → only-numeric. So `tools.rolling_zscore(fred_dgs10_df)`, `tools.compute_indicators(fred_dgs10_df, which=("rsi",))`, `tools.detect_channels(fred_dgs10_df)` all work out of the box on FRED macro frames without specifying `column=`. Pass `price_col=` / `column=` only when you want to override the auto-pick. Multi-column indicators that genuinely need OHLC (ATR) are silently skipped on non-OHLCV frames rather than erroring.

Don't gate by source — the user is reasonable and knows what they're asking for. If they want RSI on a yield series, compute it.

Cards (Phase 3 — `from quant_radar import tools`):
| Tool | Purpose |
|---|---|
| `tools.create_dashboard_card(type, title, data_refs, chart_spec=None, analysis_markdown=None, news=None, target="working")` | Create + persist a **new** card. Defaults to working. Returns the card dict (with new UUID). |
| `tools.update_card(card_id, target="working", *, title=None, chart_spec=None, data_refs=None, analysis_markdown=None, news=None, layout=None)` | Modify an existing card in-place. Only-set fields are updated; the ID stays stable. Use this for *"Add RSI and ATR to this chart"*. Returns the updated card dict, or `None` if the id wasn't found. |
| `tools.save_card_to_dashboard(card_id)` | Promote a working card into main. Main-only; no `target` kwarg. |
| `tools.remove_card(card_id, target="working")` | Delete by id. |
| `tools.add_annotation(card_id, annotation, target="working")` | Append a user-drawn line/shape/text. |
| `tools.load_dashboard(target="main")` | Return all cards as JSON dicts. |
| `tools.persist_dashboard(target="working")` | Return current card count (write-through; mostly a confirm). |
| `tools.new_working_dashboard()` | Start (or re-open) a working session — empty. Working tab appears in the viewer immediately. |
| `tools.close_working_dashboard()` | End the working session entirely — Working tab disappears. Symmetric to `new_working_dashboard`. |

Card types: `chart`, `news`, `sentiment`, `analysis`, `combo`. Card specs are tiny — they reference data via `DataRef` (source/kind/name/interval), never embed it.

**Lifecycle.** Working tab is shown if `working.json` exists (open session). `new_working_dashboard` opens it (empty list); `close_working_dashboard` removes the file. The viewer auto-refreshes both states.

Viewer (Phase 14 — React + FastAPI):
- Run with **`make app`** — launches FastAPI (serves API + built React bundle) and ttyd (host shell). Open `http://127.0.0.1:8000`.
- For dev with HMR: `make dev` runs FastAPI + ttyd + Vite. Open `http://127.0.0.1:5173`.
- The viewer is a React SPA polling `/api/cards/{main,working}`. It does **not** create or modify cards — the agent does that by calling the Python tools (which update `data/cards/main.db` and `data/cards/working.json` directly).
- Toggle "Show terminal" in the sidebar for the embedded Claude Code panel. Drag its top edge to resize.
- Cards are drag-to-move and drag-to-resize in the grid; click ⛶ to enlarge to a full-screen modal with Plotly draw tools.
- Tabs: **Main** is always shown; **Working** appears only when the working dashboard has cards.
- Density slider (1–4 columns), auto-refresh slider (2–30 s).
- Click ⛶ on a card to enlarge — the enlarged view enables Plotly's draw tools (line, openpath, rect, erase). To persist a shape, ask the agent to call `add_annotation` with the coordinates.

Pattern detection (Phase 5):

| Tool | Returns / behavior |
|---|---|
| `tools.detect_channels(df, lookback=60, confidence_threshold=0.6)` | dict with `found`, `confidence`, `slope_upper/lower`, `intercept_upper/lower`, `touches_*`, `r2_*`, `direction`. **Do not draw if `confidence < threshold`.** |
| `tools.detect_breakouts(df, channel=None, use_atr_filter=True)` | dict with `found`, `direction` ("up"/"down"), `boundary`, `margin`. If `channel` omitted, auto-detected first. |
| `tools.detect_patterns_vision(df, asset_name, title=None)` | dict with `image_path` and `instructions`. **Then call your Read tool on `image_path`** to view the chart and interpret patterns yourself. No API call. |
| `tools.channel_annotations(df, channel)` | returns 2 Annotation dicts (upper + lower trendlines) — feed to `add_annotation` to draw the channel on a card. |

**Default to the vision path** (`detect_patterns_vision` → `Read` the PNG → identify patterns). Fall back to `detect_channels` only if no high-confidence visual pattern is found, or the user explicitly asks for the algorithmic detector. Threshold ≥ 0.7 for vision, ≥ 0.65 for algorithmic. If neither clears, say plainly that no pattern was found at high enough confidence — do not draw.

News + sentiment (Phase 6):

| Tool | Purpose |
|---|---|
| `tools.fetch_news(query, source="gdelt", start, end, max_items=20)` | GDELT (no key) or Finnhub (requires `FINNHUB_API_KEY` + start/end for company news). Returns `list[dict]` of normalized news items. |
| `tools.fetch_top_headlines(source="gdelt", category="general", max_items=10)` | Latest global headlines (GDELT) or curated finance feed (Finnhub general). |
| `tools.summarize_news(items)` | **LLM-first**: returns `{items, instructions}`. You (the agent) read the items and write the summary directly. May then call `create_dashboard_card(type="news", news=items, analysis_markdown=summary)` to persist. |
| `tools.score_sentiment(items, topic=None)` | **LLM-first**: same shape. You score each item bullish/bearish/neutral and produce an overall label. Be conservative — when in doubt, choose neutral. |

The summarize/score tools deliberately don't call any external LLM API; you are the LLM. A deterministic FinBERT scorer can be added later behind a `method="finbert"` flag.

**This is the full tool surface for Phases 1–6.** The product spec is now functionally complete.

## Running code (mandatory: Docker only)

**Every command that executes project code runs inside the Docker sandbox.** This includes pytest, ruff, pyright, ad-hoc Python REPLs, agent tool calls, and any source-adapter call. The local `.venv` exists only for IDE language servers (autocomplete, jump-to-def) — it is never used to run the code itself.

### How the agent invokes the tools

When you're acting as the chat agent (inside `make app`'s terminal panel, in a `claude` session, etc.), you have **two valid paths** to invoke the tools — use one of them. **Never** try `python -c` on the host: `quant_radar` isn't installed on the host venv (Docker-only policy), and you'll waste retries on `ModuleNotFoundError`.

**Path A — REST API (preferred for quick card creation, the FastAPI server is already running):**
```bash
# Create a chart card on the working dashboard
curl -s -X POST http://127.0.0.1:8000/api/cards \
    -H 'Content-Type: application/json' \
    -d '{
      "type": "chart",
      "title": "BTC — 5y daily",
      "data_refs": [{"source":"binance","kind":"ohlcv","name":"BTCUSDT"}],
      "chart_spec": {"overlays":["sma_50","sma_200"], "subplots":["yoy"]}
    }'
```
See `GET http://127.0.0.1:8000/api/docs` for the full schema.

**Path B — Python REPL in the sandboxed container (for analytics, detection, complex flows):**
```bash
make docker-shell
>>> from quant_radar import tools
>>> from quant_radar.sources import yfinance_src
>>> df = yfinance_src.fetch_ohlcv("BTC-USD")
>>> ma = tools.analyze_moving_averages(df, asset="BTC-USD")
>>> tools.create_dashboard_card(type="analysis", title="BTC MA state",
...     analysis_markdown=ma["summary"])
```

If you find yourself running `python -c ...` directly on the host, stop. Use one of the two paths above.

### Self-check (binding for every Claude session)

Before running any command, ask yourself: *does this execute project code?* If yes, it must be one of:
- `make docker-build` / `make docker-check` / `make docker-lint` / `make docker-type` / `make docker-test`
- `make docker-shell` / `make docker-ui`
- A direct `docker run --rm --read-only --tmpfs /tmp --tmpfs /app/data --security-opt no-new-privileges --cap-drop ALL quant-radar:dev …`

**Forbidden** (immediate stop and fix):
- `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/pyright`
- `python -c "..."`, `python script.py`, `python -m …` outside the container
- `streamlit run …` outside the container
- `uv pip install …` outside the container (rebuild the image instead)

After every phase, scan your tool calls in the session and verify the rule above held. If you slipped, say so plainly and re-run in Docker before committing.

The container is read-only, drops all Linux capabilities, has `no-new-privileges`, has tmpfs for `/tmp`, and only bind-mounts `./data` for the cache. Malicious responses from external APIs cannot persist outside the cache.

| Task | Command |
|---|---|
| Lint + types + tests (commit gate) | `make docker-check` |
| Just tests | `make docker-test` |
| Just lint | `make docker-lint` |
| Just typecheck | `make docker-type` |
| Python REPL in the sandbox | `make docker-shell` |
| Streamlit UI in the sandbox | `make docker-ui` (later phases) |
| Rebuild the image (new dep, code change) | `make docker-build` |

**No phase commits until `make docker-check` is fully green.**

## Git etiquette (binding for any Claude session)

- The canonical remote for `quant_radar` is **GitHub** (`github`). All pushes go there: `git push github <branch>`.
- `origin` is the legacy GitLab remote — **do not push to it**. It's kept for history only.
- Push **only** feature branches named `phase-N-<slug>` or `fix-<slug>`. Never push to `main`.
- The user merges branches into `main` via GitHub PR. Do not attempt to merge locally and push.
- Never operate outside `/Users/cristianisac/Documents/claude_agents/quant_radar/`.
- Never commit anything under `data/cache/`, `data/cards/main.db`, or `data/cards/working.json` (already in `.gitignore`).

## Phase discipline

- Update `plan/PROGRESS.md` and `plan/plan.yaml` at the start and end of each phase.
- Run `ruff check`, `pyright`, `pytest` before committing.
- If tests fail and three iterations do not fix them, pause and ask the user.

## Style

- Pydantic v2 for all tool inputs/outputs.
- No comments unless the *why* is non-obvious.
- Tools return JSON-serializable dicts (or Pydantic models with `.model_dump()`).
- One tool per intent. Compose by chaining — don't build a god tool.
