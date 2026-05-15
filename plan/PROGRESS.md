# Progress

_Last updated: 2026-05-15_

Status legend: ☐ todo · ◐ in progress · ☑ done · ✕ skipped

## Phase 0 — Repo scaffold ◐
- ☑ `pyproject.toml` with uv + dev deps
- ☑ `.gitignore` (3-layer protection: dir, extensions, future pre-commit hook)
- ☑ `README.md`
- ☑ `SKILL.md` v1 (agent contract + git etiquette)
- ☑ `plan/PROGRESS.md` and `plan/plan.yaml`
- ☑ Package skeleton: `quant_radar/{core,sources,cache,analytics,tools,cards,dashboard,ui}`
- ☑ Pydantic types: `TimeSeries`, `OHLCV`, `NewsItem`
- ☑ Path config (`quant_radar.core.config.paths`)
- ☑ Smoke tests
- ◐ Lint + typecheck + tests green
- ☐ Initial commit, branch `phase-0-scaffold`, push to GitLab

## Phase 1 — Cache + sources ☐
- ☐ `cache.store` — read/write parquet by key, merge-append, TTL
- ☐ `sources.base` — Protocol + registry
- ☐ `sources.yfinance` adapter (prices/OHLCV)
- ☐ `sources.fred` adapter (macro)
- ☐ `sources.coinpaprika` adapter (crypto)
- ☐ Tests for each source (mocked HTTP)

## Phase 2 — Indicators ☐
- ☐ `analytics.indicators` (pandas-ta wrappers)
- ☐ `tools.compute_returns`
- ☐ `tools.compute_indicators`
- ☐ `tools.analyze_moving_averages` (above/below, MA cross state, catching-up logic)
- ☐ Tests with synthetic series

## Phase 3 — Card persistence ☐
- ☐ `cards.spec` — Card Pydantic model + DataRef
- ☐ `cards.store` — SQLite for main, JSON for working
- ☐ Tools: `create_dashboard_card`, `save_card_to_dashboard`, `remove_card`, `enlarge_card`, `persist_dashboard`, `load_dashboard`
- ☐ Reload from disk on start
- ☐ Tests

## Phase 4 — Streamlit viewer ☐
- ☐ Main / Working tabs
- ☐ Density slider (column count) to fit more cards
- ☐ `streamlit-elements` drag/move
- ☐ Click-to-enlarge modal
- ☐ `streamlit-drawable-canvas` on enlarged charts
- ☐ Auto-refresh on file change
- ☐ Pre-commit hook for large-file protection

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
