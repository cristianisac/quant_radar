# quant_radar — context for Claude Code

AI-native market research dashboard. Chat-first: the user drives a Claude
Code session in a terminal panel; the agent fetches data via Python tools
and creates / updates dashboard cards that render in a React + Plotly UI.

## Read these on every session start

**Before responding to the user's first request, read both `SKILL.md` and
`TOOLS.md` fully.** This loads the project's tool / source / kind surface
into context so the first response can dispatch immediately instead of
discovering capabilities mid-request. ~2s extra on session start saves
5-10s on every subsequent prompt because Claude won't need to grep for
what's available.

## Where the rules live

- **`SKILL.md`** is the canonical guide. Read it at the start of every
  session. It covers: tool catalog, source catalog, card lifecycle,
  the waterfall for adding new sources, the discovery contract, the
  date-range parsing rules, the pattern-detection UX, and every
  hard-won lesson from prior phases.
- This file (`CLAUDE.md`) is the **short, durable context** — the
  architectural decisions we don't want to re-litigate every session.
- If `CLAUDE.md` and `SKILL.md` ever disagree, `SKILL.md` wins (it's
  the operational reference; this file is the rationale).

## Architecture summary

```
quant_radar/
  sources/        Source ABC + per-source adapters (yfinance, binance, fred, ...)
  tools/          Agent-callable tools (data, analytics, patterns, cards, news)
  cards/          Card spec + store (working: JSON, main: SQLite)
  server/         FastAPI routes (/api/cards, /api/data, /api/sources, ...)
  analytics/      Indicator + pattern primitives (no agent surface)
quant_radar-ui/   React + Plotly + react-grid-layout viewer
```

Three persistence boundaries: **working** (per-session scratchpad,
auto-cleared on `new_working_dashboard`), **main** (durable, SQLite),
**data cache** (`data/cache/`, parquet by source/symbol/interval).

## Decisions that should not be reversed without explicit discussion

1. **Source ABC contract** — every time-series source implements
   `supports / fetch / search / describe / list_all`. News sources have
   their own contract (return `list[dict]` of articles, not DataFrames)
   and intentionally don't conform. The integration audit
   (`scripts/integration_audit.py`) enforces both.
2. **Analytical tools are column-agnostic.** Auto-pick `close` →
   `value` → only-numeric. No source gating. The user decides what
   makes sense. Indicators that genuinely need multi-column OHLC (ATR)
   silently skip when columns aren't present rather than aborting.
3. **Parametric indicator keys.** `sma_<N>` / `ema_<N>` / `rsi_<N>` /
   `atr_<N>` for any N ≥ 2 — both Python tools and the chart renderer
   parse the period from the key. No code edit for new periods.
4. **The new-source waterfall** (see SKILL.md):
   - For ad-hoc answers: **MCP first** (OpenBB MCP installed at user
     scope) → vendor MCP → raw HTTP.
   - For card-integrated sources: **OpenBB Platform provider first**
     (one install, ~20 LOC subclass per provider) → dedicated Python
     lib → hand-written.
5. **Pattern detection defaults to vision** (`detect_patterns_vision`
   → render PNG → agent reads it visually) and falls back to the
   algorithmic detector. Confidence thresholds: 0.7 vision, 0.65 algo.
6. **Cards are agent-created, never user-created in the UI.** The UI
   is read-only viewer + manual refresh/save/delete/clear actions.
   New cards always come from `tools.create_dashboard_card(...)`.
7. **Docker for runtime execution** of Python code. Host venv exists
   only for IDE language servers (pyright/ruff). All API fetches +
   tool runs go through containers with `--env-file .env`. UI builds
   on host (Vite) → bundle baked into image.
8. **Git workflow**: feature branches, squash-merge via `gh pr merge
   --squash --delete-branch`. The default remote is `github`.

## Security posture

- `.env` holds API keys (FRED_API_KEY, FINNHUB_API_KEY, FMP_API_KEY,
  TIINGO_API_KEY, POLYGON_API_KEY). Permissions 600, gitignored.
- Never echo `.env` values in chat or commits. Use `grep -c` or
  `read -s` patterns; redact `apikey=`/`token=` in any logged URLs.
- Containers run with `--read-only --tmpfs /tmp --tmpfs /app/data
  --security-opt no-new-privileges --cap-drop ALL`.

## Authoritative source list (current)

| Source | Native ABC? | Key needed? | Notes |
|---|:---:|:---:|---|
| yfinance | ✅ | no | OHLCV — equities, ETFs, indices, FX, crypto via `*-USD` |
| binance | ✅ | no | OHLCV — ~2k spot pairs, most reliable rate limit |
| fred | ✅ | yes (metadata only) | macro — native frequency per series |
| gdelt | – (news) | no | global news, Lucene syntax, flaky |
| finnhub | – (news) | yes | curated finance news, 60 calls/min |
| FMP | ❌ via OpenBB MCP | yes | equity fundamentals + OHLCV, 250 req/day free |
| Tiingo | ❌ via OpenBB MCP | yes | equity OHLCV + IEX intraday, 1000 req/hr free |
| Polygon | ❌ via OpenBB MCP | yes | intraday equity/crypto, 5 calls/min free |

When the user asks for FMP/Tiingo/Polygon data: reach for the OpenBB
MCP (`mcp__openbb__*` tools), not a new native adapter. If the use
case becomes recurring, *then* graduate it to a `_OpenBBSource`
subclass per the waterfall.

## Verification commands

```bash
# Inside the repo root:
make docker-build && /Applications/Docker.app/Contents/Resources/bin/docker run \
  --rm --read-only --tmpfs /tmp --tmpfs /app/data \
  --security-opt no-new-privileges --cap-drop ALL \
  quant-radar:dev pytest -q -p no:cacheprovider

# End-to-end alignment audit (catalog + ABC contract + tools live):
/Applications/Docker.app/Contents/Resources/bin/docker run \
  --rm --read-only --tmpfs /tmp --tmpfs /app/data \
  --security-opt no-new-privileges --cap-drop ALL \
  --env-file .env -v "$(pwd)/scripts:/app/scripts:ro" \
  quant-radar:dev python scripts/integration_audit.py
```

Target: pytest all green, audit 100% pass. Both must stay green for
PRs.
