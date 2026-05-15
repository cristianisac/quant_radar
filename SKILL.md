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

**Available now (Phases 1–2):**

Data sources (return `pandas.DataFrame` with `DatetimeIndex` named `timestamp`):
| Tool | Purpose |
|---|---|
| `quant_radar.sources.yfinance_src.fetch_ohlcv(symbol, interval="1d", start, end, refresh)` | yfinance OHLCV — equities, ETFs, FX, indices. Defaults to 5y of daily history if `start` is omitted. |
| `quant_radar.sources.binance_src.fetch_ohlcv(symbol, interval="1d", start, end, refresh)` | **Primary crypto source.** Binance public spot API, no key, no signup. Bare symbols (`BTC`, `ETH`, `SOL`) map to `*USDT`; pre-formed pairs (`BTCUSDT`) pass through. |
| `quant_radar.sources.fred_src.fetch_macro_series(series_id, start, end, refresh)` | FRED macro (DGS10, CPIAUCSL, etc.). No API key. |
| `quant_radar.sources.coinpaprika_src.fetch_ohlcv(coin_id, ...)` | **Deferred** — CoinPaprika moved historical OHLCV behind a paid plan; the free tier returns 402. Use `binance_src` for crypto instead. |

Cache TTL: 5min intraday / 24h daily / 7d macro. Within TTL the cache is authoritative — only `refresh=True` or expired TTL triggers a real fetch.

Analytics (importable as `from quant_radar import tools`):
| Tool | Returns |
|---|---|
| `tools.compute_returns(df, periods=("1d","1w","1m","1y","yoy","ytd"))` | `dict[str, float \| None]` |
| `tools.compute_indicators(df, indicators=("sma_50","sma_200","rsi","atr","macd"))` | enriched DataFrame |
| `tools.analyze_moving_averages(df, fast_period=50, slow_period=200, asset="X")` | dict with above/below 50d/200d, 50d-vs-200d, catching-up-from-below, golden/death cross, summary |
| `tools.analyze_indicators(df)` | `{"rsi_state": "overbought\|oversold\|neutral", "volatility_regime": "high\|elevated\|normal\|low"}` |

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

Viewer (Phase 4):
- Run with `make docker-ui` → opens at `http://localhost:8501`.
- Read-only Streamlit app. It does **not** create or modify cards — it reads `data/cards/main.db` and `data/cards/working.json` and renders.
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

**The pattern-detection UX is mandatory.** When the user asks for channels, breakouts, or patterns, **ask first**:

> "Algorithmic detectors, LLM-vision detectors, or both?"

Then call the corresponding tool(s). If confidence is below threshold, do not draw — say plainly that no pattern was found at high enough confidence.

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

**Every command that executes project code runs inside the Docker sandbox.** This includes pytest, ruff, pyright, ad-hoc Python REPLs, agent tool calls, the Streamlit UI, and any source-adapter call. The local `.venv` exists only for IDE language servers (autocomplete, jump-to-def) — it is never used to run the code itself.

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
