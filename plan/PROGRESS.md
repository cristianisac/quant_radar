# Progress

_Last updated: 2026-05-15_

Status legend: ☐ todo · ◐ in progress · ☑ done · ✕ skipped

## Phase 0 — Repo scaffold ☑
- ☑ `pyproject.toml` with uv + dev deps
- ☑ `.gitignore` (3-layer protection)
- ☑ `README.md`
- ☑ `SKILL.md` v1 (agent contract + git etiquette)
- ☑ `plan/PROGRESS.md` and `plan/plan.yaml`
- ☑ Package skeleton
- ☑ Pydantic types: `TimeSeries`, `OHLCV`, `NewsItem`
- ☑ Path config
- ☑ Smoke tests (6 passing)
- ☑ Committed and pushed on branch `phase-0-scaffold`

## Phase 1 — Cache + sources + sandbox ☑
- ☑ `cache.store` — parquet store, smart merge, TTL-gated refresh
- ☑ `sources.base` — TTL constants
- ☑ `sources.yfinance_src` — OHLCV adapter
- ☑ `sources.fred_src` — macro via fredgraph.csv (no API key)
- ☑ `sources.coinpaprika_src` — crypto OHLCV via REST
- ☑ Tests: 26 passing (cache: 10, sources: 10 mocked, smoke: 6)
- ☑ Dockerfile + docker-compose.yml + Makefile for sandboxed runs
- ☑ Tests verified inside the sandboxed container

## Phase 2 — Indicators ☑
- ☑ `analytics.indicators` — sma, ema, rsi (Wilder), atr (Wilder), macd. Hand-rolled in pure pandas (avoided pandas-ta's Python 3.13 incompatibility)
- ☑ `analytics.returns` — `compute_returns` over 1d/1w/1m/1y/yoy/ytd
- ☑ `analytics.ma` — `analyze_moving_averages` answers all spec questions (above/below 50d/200d, 50d vs 200d, catching-up-from-below, golden/death cross)
- ☑ `analytics.regime` — RSI state, ATR volatility regime
- ☑ `tools.compute_returns`, `tools.compute_indicators`, `tools.analyze_moving_averages`, `tools.analyze_indicators`
- ☑ 49 tests passing (indicators, returns, MA, tool wrappers)
- ☑ Docker-only execution policy enforced via `make docker-check`

## Phase 3 — Card persistence ☑
- ☑ `cards.spec` — `Card`, `DataRef`, `ChartSpec`, `Annotation`, `LayoutHint`. `extra="forbid"` blocks unknown fields.
- ☑ `cards.store` — SQLite for main (auto-schema), JSON for working
- ☑ `tools.create_dashboard_card`, `save_card_to_dashboard` (promote working → main), `remove_card`, `persist_dashboard`, `load_dashboard`, `new_working_dashboard`, `add_annotation`
- ☑ Reload-on-start via simple read-from-disk
- ☑ 68 tests passing in the sandbox

## Phase 4 — Streamlit viewer ☑
- ☑ Main / Working tabs (Working tab only appears when working dashboard has cards)
- ☑ Density slider (1–4 cards per row)
- ☑ Click-to-enlarge dialog (`st.dialog`)
- ☑ Plotly built-in shape drawing in enlarged view (line, openpath, rect, erase)
- ☑ Auto-refresh via `streamlit-autorefresh` (2–30s)
- ☑ DataRef hydration via cache (no network within TTL)
- ☑ Card type renderers: chart (candlestick + overlays + subplots + annotations), news, sentiment, analysis
- ☑ 77 tests passing in the sandbox
- ◐ Drag-to-move via `streamlit-elements` — deferred (st.columns grid + density slider covers density; drag adds complexity, defer to Phase 4.5 if needed)
- ◐ Persisting drawn shapes back to disk — currently drawings are visual-only; saving is via the agent calling `add_annotation`

## Phase 5 — Pattern detection ☑
- ☑ `analytics.patterns.detect_channel` — scipy.signal.find_peaks for swing points + linregress on highs/lows; confidence = 0.4·parallelism + 0.4·R² + 0.2·touches
- ☑ `analytics.patterns.detect_breakout` — last-bar vs channel boundary with optional ATR-multiple noise filter
- ☑ `analytics.patterns.channel_to_annotation_points` — converts channel slopes to (ts, price) trendline endpoints
- ☑ `analytics.vision.render_chart_png` — matplotlib OHLCV/line rendering, written under `data/cache/vision/`
- ☑ `tools.detect_channels`, `tools.detect_breakouts`, `tools.detect_patterns_vision`, `tools.channel_annotations`
- ☑ Vision tool returns `{image_path, instructions}` — the calling Claude session reads the PNG with its own Read tool (no Anthropic SDK / API key needed)
- ☑ Confidence gating built into the return; agent contract in SKILL.md says "don't draw below threshold"
- ☑ 92 tests passing in the sandbox

## Phase 11 — Durable source-onboarding policy + GDELT verdict ☑
- ☑ `scripts/probe_gdelt.py` — definitive GDELT reliability probe (6 queries × 2 windows = 12 combinations)
- ☑ **GDELT verdict**: works ~83% of the time, latency 7–87s, `OR` queries return 0 items consistently → marked as opportunistic-only; recommend `finnhub` (free key) for critical news. Catalog updated with the realistic note.
- ☑ **SKILL.md "Adding a new data source" checklist** — 12-step procedure codifying every bug we hit (default lookback, tz-naive timestamps, empty responses, native frequency, rate limits, paid-tier surprise, symbol normalization, live verification mandate). Bound on every Claude Code session that touches this project.
- ☑ Cheatsheet block in SKILL.md marks Binance "most reliable", Finnhub "use when news matters", GDELT "opportunistic only".

## Phase 10 — Source catalog + introspection + edge-case fixes ☑

### Static catalog
- ☑ `quant_radar.sources.catalog` — `SourceCapability` per source: intervals, history concept, coverage, auth, rate-limit, status, examples
- ☑ Verified history depths live (probe with `start=2000-01-01`):
  - **Binance**: BTC/ETH from 2017-08-17 (Binance launch), BNB 2017-11-06, XRP 2018-05-04, SOL 2020-08-11
  - **yfinance**: AAPL/MSFT/SPY/NVDA from at least 2000-01-03 (and earlier), TSLA 2010-06-29 IPO, BTC-USD 2014-09-17
  - **FRED**: DGS10 daily from 1962, CPIAUCSL monthly from 1947, GDP quarterly from 1947 — *native frequency varies per series*

### Dynamic introspection
- ☑ `tools.list_sources()` — every source's capabilities as JSON-serializable dicts
- ☑ `tools.describe_source(name)` — single-source lookup
- ☑ `tools.probe_history(symbol, source, kind)` — hits the API with `refresh=True`, reports actual `first`/`last`/`bars` for a specific asset

### Bug fixes surfaced during the catalog work
- ☑ Cache `get_or_fetch(refresh=True)` was using the fresh DataFrame directly without tz-normalizing → `_slice` crashed comparing tz-naive (yfinance) vs tz-aware (UTC) bounds. Now always normalizes via `_ensure_index` before write/slice.
- ☑ `_ensure_index` handled empty DataFrames poorly (raised when there was no `timestamp` column and no DatetimeIndex). Now returns an empty UTC-aware DataFrame, preserving the contract for sources that legitimately return no rows.
- ☑ GDELT `ReadTimeout`/`ConnectTimeout` now retry with the same back-off schedule as 429s; timeout bumped 15s → 30s for the public free endpoint.

- ☑ 144 tests passing in the sandbox; live probe + E2E re-run after fixes (all 12 scenarios green).

## Phase 9 — E2E fixes (Bugs A/B/C from the live run) ☑
- ☑ **Bug A** — yfinance defaulted to 1 month (broke 200d SMA). Adapter now injects a sensible default `start` per interval (5y daily / 90d intraday / etc).
- ☑ **Bug B** — CoinPaprika moved OHLCV behind a paywall (402). Added `binance_src.py` — no key, no signup, 1200 req/min; pagination over `_LIMIT_MAX`; bare base symbols map to `*USDT`. CoinPaprika marked deferred. `ui.data.hydrate` learned the new source.
- ☑ **Bug C** — GDELT 429 retry with back-off (1s, 3s); raises only after all retries exhausted.
- ☑ Cosmetic: `MPLCONFIGDIR=/tmp/matplotlib` in the Dockerfile silences the read-only-config warning.
- ☑ E2E demo (`scripts/e2e_demo.py`) added and run live — all 12 scenarios green: BTC MA analysis, ETH channel detect (conf 0.833), NVDA YoY (+68%), SOL via Binance (1825 bars), DGS10 (4.46%, 16k bars), news, update_card, save-to-main, new working dashboard, multi-asset screen (MSFT flagged catching-up), vision PNG (5y chart), close working dashboard.
- ☑ 131 tests passing in the sandbox.

## Phase 8 — Hardening (pre-mortem mitigations) ☑
- ☑ SQLite WAL mode in `cards.store._connect` — Streamlit viewer can read while the agent writes; no more "database is locked" risk
- ☑ Streamlit host port bound to `127.0.0.1:8501` (was `0.0.0.0:8501`) — viewer is loopback-only on the host
- ☑ `tests/test_skill_md_sync.py` — every `tools.<name>` mentioned in SKILL.md must exist in `tools.__all__`, and every exported tool must be callable. Catches doc/code drift.
- ☑ Enlarge dialog: caption upgraded to a `st.warning` so users don't expect drawn shapes to persist
- ☑ Channel detector defaults tightened: composite threshold 0.6 → 0.65; new `min_r2=0.55` gate requires both trendlines to fit individually before `found=True`
- ☑ SKILL.md is now included in the Docker image (so the sync test can run inside)
- ☑ 121 tests passing in the sandbox

## Phase 7 — Card-update + working-session fixes ☑
- ☑ `tools.update_card(card_id, **fields)` — modify existing card in-place, stable id. Closes the *"Add RSI and ATR to this chart"* gap.
- ☑ `tools.close_working_dashboard()` — removes `working.json`, Working tab disappears. Symmetric to `new_working_dashboard`.
- ☑ Viewer tab visibility now keyed on `working.json` existence, not card count — Working tab appears as soon as the session is opened.
- ☑ `save_card_to_dashboard` tightened to main-only (no more no-op `target="working"` path).
- ☑ 118 tests passing in the sandbox.

## Phase 6 — News + sentiment ☑
- ☑ `sources.gdelt_src` — public GDELT DOC API, no key. Default last-24h timespan; explicit start/end uses `startdatetime`/`enddatetime`.
- ☑ `sources.finnhub_src` — Finnhub free tier (requires `FINNHUB_API_KEY`); raises a clear error if the key is missing. Both general and company-news endpoints.
- ☑ `tools.fetch_news` — routes to GDELT (default) or Finnhub (company news, requires start/end)
- ☑ `tools.fetch_top_headlines` — GDELT global feed or Finnhub general
- ☑ `tools.summarize_news` — LLM-first: returns `{items, instructions}` for the calling agent to summarize
- ☑ `tools.score_sentiment` — LLM-first: same shape; takes optional `topic`. FinBERT path deferred behind a future `method` flag
- ☑ News card type renderer already present from Phase 4
- ☑ 109 tests passing in the sandbox
