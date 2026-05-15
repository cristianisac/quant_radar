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

## Phase 5 — Pattern detection ☐
- ☐ `analytics.channels` (linear regression on swing highs/lows)
- ☐ `analytics.breakouts`
- ☐ `tools.detect_channels`, `tools.detect_breakouts`
- ☐ `tools.detect_patterns_vision` (Claude vision via Bash)
- ☐ Confidence gating
- ☐ SKILL.md update: "ask algo / vision / both"

## Phase 6 — News + sentiment ☐
- ☐ `sources.gdelt`, `sources.finnhub`
- ☐ `tools.fetch_news`, `tools.fetch_top_headlines`
- ☐ `tools.summarize_news` (LLM)
- ☐ `tools.score_sentiment` (LLM-first; FinBERT as flag, deferred)
- ☐ News card type + renderer
