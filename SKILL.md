---
name: quant-radar
description: AI-native market research dashboard. Use these tools to fetch market/macro/news data, run technical analysis, and create cards on the user's main or working dashboard. The user talks to you; you call tools and persist cards. Cards live on disk; a separate Streamlit viewer reads them.
---

# Quant Radar — agent contract

This file is the manifest for Claude Code sessions working on or with `quant_radar`. Read it on every turn that involves the project.

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

## Pattern detection UX

When the user asks for channels, patterns, or breakouts, **ask first**:

> "Algorithmic detectors, LLM-vision detectors, or both?"

Then call the corresponding tool(s). If confidence is below threshold, do not draw — say so plainly.

## Tools

_(catalog grows each phase; see `plan/PROGRESS.md` for status)_

**Available now (Phase 1):**

| Tool | Purpose |
|---|---|
| `quant_radar.cache.get_or_fetch(key, fetcher, ...)` | Read from disk cache or call fetcher for the missing range. Pass `refresh=True` to force. |
| `quant_radar.sources.yfinance_src.fetch_ohlcv(symbol, interval="1d", start, end, refresh)` | yfinance OHLCV — equities, ETFs, FX, indices, BTC-USD etc. |
| `quant_radar.sources.fred_src.fetch_macro_series(series_id, start, end, refresh)` | FRED macro (DGS10, CPIAUCSL, etc.). No API key. |
| `quant_radar.sources.coinpaprika_src.fetch_ohlcv(coin_id, start, end, refresh)` | Crypto OHLCV from CoinPaprika (`btc-bitcoin`, `eth-ethereum`, etc.). |

Cache TTL: 5min intraday / 24h daily / 7d macro. Within TTL the cache is authoritative — only `refresh=True` or expired TTL triggers a real fetch.

**Planned for later phases:**
- Phase 2: `compute_returns`, `compute_indicators`, `analyze_moving_averages`
- Phase 3: `create_dashboard_card`, `save_card_to_dashboard`, `remove_card`, `enlarge_card`, `persist_dashboard`, `load_dashboard`
- Phase 5: `detect_channels`, `detect_breakouts`, `detect_patterns_vision`
- Phase 6: `fetch_news`, `summarize_news`, `score_sentiment`

## Running fetches safely

Any tool that hits a real external API should be exercised inside the Docker sandbox:

```bash
make docker-shell   # then call the tools from a Python REPL
make docker-test    # full test suite in the sandbox
```

The container is read-only with dropped capabilities; only `./data` is writable. Malicious responses cannot persist outside the cache.

## Git etiquette (binding for any Claude session)

- Push **only** to the `origin` remote of this repo. Never add or push to any other remote.
- Push **only** feature branches named `phase-N-<slug>` or `fix-<slug>`. Never push to `main`.
- The user merges branches into `main` via GitLab MR. Do not attempt to merge locally and push.
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
