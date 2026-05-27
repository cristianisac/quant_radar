Extensions to add: benzinga@1.6.1, bls@1.3.1, cftc@1.4.1, commodity@1.5.2, congress_gov@1.2.3, crypto@1.6.2, currency@1.6.2, derivatives@1.6.2, econdb@1.5.1, economy@1.6.2, equity@1.6.2, etf@1.6.2, federal_reserve@1.6.2, fixedincome@1.6.2, fmp@1.6.1, fred@1.6.1, government_us@1.6.1, imf@2.1.3, imf_utils@2.1.3, index@1.6.2, intrinio@1.6.1, news@1.6.2, oecd@1.6.1, regulators@1.6.2, sec@1.6.1, tiingo@1.6.1, tradingeconomics@1.6.1, us_eia@1.3.1, uscongress@1.2.3, yfinance@1.6.3

Building...
# quant_radar — Tool & Data Surface

**Generated**: this file is produced by `scripts/generate_tools_doc.py` from the live registry (`CATALOG` + `tools.__all__` + `kind_relationships`). Last regenerated 2026-05-27.

Do not edit by hand — change the registry instead, then regenerate. A pytest assertion guards against drift.

---

## 1. Data sources & coverage with our authentication

Each row is a (source, kind) pair. **Verified** means the integration audit successfully fetched real data using the keys in our `.env`. Failures keep the upstream error so you can see *why* a pair isn't accessible.

### `alphavantage`

- **Auth**: ALPHAVANTAGE_API_KEY env var (free signup at alphavantage.co/support/#api-key)
- **Rate limit**: 25 req/day, 5 req/min — TIGHT. Cache aggressively.
- **Status**: active
- **Coverage**: Global stocks + ETFs + crypto + FX. ML-based per-ticker sentiment scoring (overall + per-symbol relevance + label).
- **Notes**: Best-quality per-ticker news sentiment scoring. Primary source in kind_coverage for kind='sentiment'. Falls back to marketaux when daily quota exhausted. See quant_radar/sources/kind_coverage.py for the full multi-source routing logic.

| kind | declared schema | verified | detail |
|---|---|:---:|---|
| `sentiment` | `sentiment_score`, `relevance_score`, `overall_score`, `sentiment_label`, `title`, `url`, `article_source`, `topics` | ❌ | RuntimeError: Alpha Vantage quota/notice: We have detected your API key as RGNWVI7R7VF34BLV and our standard API rate limit is 25 requests per day. Please subscribe to any of the premium plans at https://www.alphavantage.co/premium/ to instan |

### `apewisdom`

- **Auth**: none
- **Rate limit**: no documented limit; unauthenticated public endpoint. Cache intraday (5 min) — leaderboard rotates throughout the day.
- **Status**: active
- **Coverage**: Tickers being discussed on tracked subreddits (WSB, wallstreetbetsELITE, stocks, investing, cryptocurrency, satoshistreetbets, ...). ~870 stocks/ETFs in `all-stocks`, ~160 crypto in `all-crypto`. Commodities/bonds surface only via listed proxies (GLD, TLT, USO).
- **Notes**: Mention-velocity signal (not classical -1..1 sentiment). Most useful as a *viral-attention* indicator: a 5×–10× spike in mentions_change_pct typically precedes meme-driven price moves. Pair with AV/Marketaux for actual sentiment polarity. Crypto tickers stored with .X suffix (BTC.X); adapter accepts either shape.

| kind | declared schema | verified | detail |
|---|---|:---:|---|
| `social_sentiment` | `ticker`, `name`, `mentions`, `mentions_24h_ago`, `mentions_change_pct`, `upvotes`, `rank`, `rank_24h_ago`, `filter` | ✅ | rows=1, schema⊆actual=True |

### `binance`

- **Auth**: none
- **Rate limit**: 1200 request-weight/min per IP — practically unlimited for cached use
- **Status**: active
- **Coverage**: 1500+ spot pairs (USDT, USDC, BUSD, FDUSD, TUSD, BTC, ETH, BNB, EUR, GBP quotes). Bare base symbols ('BTC', 'ETH', 'SOL') are auto-mapped to '*USDT'.

| kind | declared schema | verified | detail |
|---|---|:---:|---|
| `ohlcv` | `open`, `high`, `low`, `close`, `volume` | ✅ | rows=1825, schema⊆actual=True |

### `finnhub`

- **Auth**: FINNHUB_API_KEY env var (free signup at finnhub.io)
- **Rate limit**: 60 calls/min on the free tier
- **Status**: active
- **Coverage**: curated finance news plus company-specific (US tickers). Insider transactions cover US-listed equities, one row per Form-4 filing.
- **Notes**: Calendars are window-scoped — ref.name accepts '7d' / '30d' / '60d' / '90d' (default 30d). Economic calendar is paid on every free provider we have keys for (FMP 402, tradingeconomics requires paid key) — deferred. ETF holdings + analyst recommendation time-series also free on Finnhub, but ETF holdings is paywalled (verified 2026-05-26). Recommendation trends + insider-sentiment MSPR ship in phase 2b.4. News-sentiment + price-target endpoints are 403 on the free tier (verified 2026-05-27).

| kind | declared schema | verified | detail |
|---|---|:---:|---|
| `news` | `title`, `url`, `source`, `published_at`, `summary` | ✅ | non-conforming surface (not ABC) |
| `insider` | `transaction_price`, `share`, `change`, `transaction_code`, `insider_name`, `filing_date`, `is_derivative`, `source` | ✅ | rows=115, schema⊆actual=True |
| `earnings_calendar` | `symbol`, `eps_estimate`, `eps_actual`, `revenue_estimate`, `revenue_actual`, `hour`, `quarter`, `year` | ✅ | rows=409, schema⊆actual=True |
| `ipo_calendar` | `symbol`, `company_name`, `exchange`, `number_of_shares`, `price`, `status`, `total_shares_value` | ❌ | rows=0, schema⊆actual=True |
| `recommendation` | `strong_buy`, `buy`, `hold`, `sell`, `strong_sell`, `symbol` | ✅ | rows=4, schema⊆actual=True |
| `insider_sentiment` | `change`, `mspr`, `symbol` | ✅ | rows=11, schema⊆actual=True |

### `fmp`

- **Auth**: FMP_API_KEY env var (free signup at financialmodelingprep.com)
- **Rate limit**: 250 req/day on free tier — modest; cache-first is essential
- **Status**: active
- **Coverage**: US equities + global ADRs + ETFs (~40k). Forex majors. Income statement / balance sheet / cash flow for ~30k tickers, quarterly + annual. Adapter wraps OpenBB Platform's `fmp` provider.
- **Notes**: OHLCV via obb.equity.price.historical; forex via obb.currency.price.historical. Fundamentals via obb.equity.fundamental.income/balance/cash with period='quarter'|'annual'. Adapter sets the DataFrame index to period_ending so each row is anchored to its fiscal period end-date.

| kind | declared schema | verified | detail |
|---|---|:---:|---|
| `ohlcv` | `open`, `high`, `low`, `close`, `volume` | ✅ | rows=251, schema⊆actual=True |
| `forex` | `open`, `high`, `low`, `close` | ✅ | rows=314, schema⊆actual=True |
| `crypto` | `open`, `high`, `low`, `close`, `volume` | ✅ | rows=251, schema⊆actual=True |
| `income` | `fiscal_period`, `fiscal_year`, `revenue`, `gross_profit`, `bottom_line_net_income` | ✅ | rows=5, schema⊆actual=True |
| `balance` | `fiscal_period`, `fiscal_year`, `total_assets`, `total_liabilities`, `total_debt` | ✅ | rows=5, schema⊆actual=True |
| `cash` | `fiscal_period`, `fiscal_year`, `operating_cash_flow`, `free_cash_flow` | ✅ | rows=5, schema⊆actual=True |
| `dividends` | `amount`, `dividend_yield`, `frequency`, `payment_date`, `record_date` | ✅ | rows=5, schema⊆actual=True |
| `splits` | `numerator`, `denominator`, `splitType` | ✅ | rows=5, schema⊆actual=True |
| `estimates` | `estimated_revenue_avg`, `estimated_eps_avg`, `estimated_ebitda_avg`, `number_analysts_eps` | ✅ | rows=10, schema⊆actual=True |
| `sec_filings` | `report_type`, `report_url`, `filing_url`, `symbol`, `cik`, `accepted_date` | ✅ | rows=20, schema⊆actual=True |

### `fred`

- **Auth**: none
- **Rate limit**: lenient
- **Status**: active
- **Coverage**: 800k+ US & international macroeconomic series via the public fredgraph.csv endpoint

| kind | declared schema | verified | detail |
|---|---|:---:|---|
| `macro` | `value` | ✅ | rows=16083, schema⊆actual=True |

### `gdelt`

- **Auth**: none
- **Rate limit**: tight; ~83% success rate on free public access; latency 7–87s; adapter retries 429/timeouts with 1s/3s back-off
- **Status**: active
- **Coverage**: global news (many languages), Lucene-style query syntax. Live-tested: single terms, AND, and quoted phrases work; OR queries returned 0 items in every test combination — prefer AND or single terms until investigated.
- **Notes**: Treat as opportunistic background news, not a critical path. For reliable news use finnhub (requires free key).

| kind | declared schema | verified | detail |
|---|---|:---:|---|
| `news` | `title`, `url`, `source`, `published_at` | ✅ | non-conforming surface (not ABC) |
| `news_tone` | `tone` | ✅ | rows=166, schema⊆actual=True |

### `marketaux`

- **Auth**: MARKETAUX_API_KEY env var (free signup at marketaux.com/account/dashboard)
- **Rate limit**: 100 req/day, 1 req/sec — more generous than AV.
- **Status**: active
- **Coverage**: Global incl. small caps + international. Wider symbol universe than Alpha Vantage but less rich per-article scoring.
- **Notes**: Fallback for kind='sentiment' when Alpha Vantage's 25/day quota is exhausted, OR for tickers AV doesn't cover. Returns per-entity sentiment_score; we derive a label heuristically (>=0.35 Bullish, ..., <-0.35 Bearish) for UI parity with AV.

| kind | declared schema | verified | detail |
|---|---|:---:|---|
| `sentiment` | `sentiment_score`, `relevance_score`, `overall_score`, `sentiment_label`, `title`, `url`, `article_source`, `topics` | ✅ | rows=3, schema⊆actual=True |

### `polygon`

- **Auth**: POLYGON_API_KEY env var (free signup at polygon.io)
- **Rate limit**: 5 calls/min on free tier — tight; cache aggressively
- **Status**: active
- **Coverage**: US equities + ETFs + indices + crypto + FX (~70k tickers). Per-ticker news with LLM-derived sentiment + reasoning + keywords. Hand-written REST adapter (Polygon not in OpenBB Platform's bundled providers).
- **Notes**: Equity aggregates use bare ticker; forex aggregates use `C:<pair>` prefix (e.g. C:EURUSD). Adapter handles the prefix internally.

| kind | declared schema | verified | detail |
|---|---|:---:|---|
| `ohlcv` | `open`, `high`, `low`, `close`, `volume` | ✅ | rows=496, schema⊆actual=True |
| `forex` | `open`, `high`, `low`, `close` | ✅ | rows=616, schema⊆actual=True |
| `ticker_news` | `title`, `author`, `publisher`, `article_url`, `sentiment`, `sentiment_reasoning`, `keywords` | ✅ | rows=50, schema⊆actual=True |

### `tiingo`

- **Auth**: TIINGO_API_KEY env var (free signup at tiingo.com — header is Token auth)
- **Rate limit**: 1000 req/hr on free tier — generous
- **Status**: active
- **Coverage**: US equities + ETFs + select global ADRs (~30k). Forex majors. Adapter wraps OpenBB Platform's `tiingo` provider.
- **Notes**: OpenBB-backed. Provides adjusted prices via adj_* columns (stripped by adapter — we keep canonical OHLCV). Crypto symbols use `<base><quote>` (BTCUSD, ETHUSD).

| kind | declared schema | verified | detail |
|---|---|:---:|---|
| `ohlcv` | `open`, `high`, `low`, `close`, `volume` | ✅ | rows=251, schema⊆actual=True |
| `forex` | `open`, `high`, `low`, `close` | ✅ | rows=314, schema⊆actual=True |
| `crypto` | `open`, `high`, `low`, `close`, `volume` | ❌ | EmptyDataError: 
[Empty] -> The response is empty |

### `yfinance`

- **Auth**: none
- **Rate limit**: aggressive — cache-first; only use refresh=True deliberately
- **Status**: active
- **Coverage**: equities, ETFs, indices (^GSPC, ^IXIC), FX (EURUSD=X), major crypto-USD pairs (BTC-USD, ETH-USD, SOL-USD)

| kind | declared schema | verified | detail |
|---|---|:---:|---|
| `ohlcv` | `open`, `high`, `low`, `close`, `volume` | ✅ | rows=1253, schema⊆actual=True |

## 2. Agent-callable tool surface

Every function exported from `quant_radar.tools`. The grouping is intent-based, not module-based. Tool count = 48.

### Card lifecycle

- `add_annotation` — Append a user-drawn annotation to a card's chart spec.
- `clear_dashboard` — Remove every card from ``target``. Returns count removed.
- `close_working_dashboard` — End the working session entirely — Working tab disappears.
- `create_dashboard_card` — Create a new card and persist it. Defaults to the working dashboard.
- `load_dashboard` — (no docstring)
- `new_working_dashboard` — Start (or re-open) a working dashboard with no cards.
- `persist_dashboard` — Force-flush any in-memory state. Returns the number of cards persisted.
- `remove_card` — (no docstring)
- `save_card_to_dashboard` — Promote a working card to the persistent main dashboard.
- `update_card` — Modify an existing card in-place. Only-set fields are updated.

### Analytical tools (column-agnostic — apply to any time series)

- `analyze_indicators` — Return state labels for RSI and (when OHLC is available) volatility.
- `analyze_moving_averages` — MA crossover state. Column-agnostic.
- `compute_indicators` — Append the requested indicator columns. Column-agnostic.
- `compute_returns` — Period-over-period returns. Works on any single price column.
- `filter_by_date` — Return rows whose index falls in ``[start, end]`` inclusive.
- `rolling_zscore` — Append a ``zscore_{window}`` column with rolling z-score.

### Pattern detection

- `channel_annotations` — Return two ``Annotation`` dicts (upper + lower) ready for ``add_annotation``.
- `detect_breakouts` — If ``channel`` is not provided, one is detected automatically first.
- `detect_channels` — Column-agnostic channel fit (close → value → only-numeric).
- `detect_patterns_vision` — Render the chart and ask the calling agent to read it.

### News tools

- `fetch_news` — Return a list of normalized news-item dicts.
- `fetch_top_headlines` — Latest headlines — GDELT for global, Finnhub for finance.
- `score_sentiment` — Structured payload for the calling LLM to score sentiment.
- `summarize_news` — Structured payload for the calling LLM to summarize.

### Sentiment + social (with multi-source routing)

- `describe_sentiment_routing` — Return the multi-source routing record for kind='sentiment'.
- `describe_social_sentiment_routing` — Return the multi-source routing record for kind='social_sentiment'.
- `fetch_attention_and_polarity` — Combine the volume axis (Apewisdom) with the polarity axis (AV/Marketaux).
- `fetch_sentiment` — Fetch per-ticker news sentiment with automatic provider fallback.
- `fetch_social_sentiment` — Fetch Reddit-mention velocity for ``ticker`` via Apewisdom.

### Discovery / source introspection

- `all_analytical_tools` — Return every analytical tool the agent can apply to a time series.
- `all_requirements` — (no docstring)
- `describe_kind_coverage` — Cross-source comparison for one ``kind`` (e.g. sentiment).
- `describe_source` — Return one source's full capability, or ``None`` if unknown.
- `describe_symbol` — Generic per-symbol metadata — works on any registered source.
- `list_all_symbols` — Enumerate every symbol/series ``source`` offers.
- `list_binance_pairs` — Enumerate Binance spot pairs (filterable by quote currency).
- `list_covered_kinds` — Kinds with multi-source coverage declared in ``kind_coverage.py``.
- `list_kind_relationships` — Every cross-kind relationship (e.g. social_sentiment ↔ sentiment).
- `list_searchable_sources` — Quick sanity probe — which sources currently support search?
- `list_sources` — Return all sources with their capabilities.
- `probe_history` — Return ``{first, last, bars}`` for an asset by hitting the API.
- `relationships_for_kind` — All cross-kind relationships that involve ``kind``.
- `requirements_for` — (no docstring)
- `search_binance` — Binance spot-pair search. Matches against pair symbol + base
- `search_fred` — FRED keyword search (~800k series). Requires ``FRED_API_KEY``.
- `search_source` — Generic discovery — search any registered source by keyword.
- `search_yfinance` — yfinance keyword search via Yahoo's quote endpoint.
- `tools_for_ref` — Return analytical tools applicable to ``ref``.

## 3. Cross-kind relationships

From `kind_relationships.py` — which data types pair / compose / extend each other.

### `attention_and_polarity` — *orthogonal*

**Kinds**: `social_sentiment`, `sentiment`

Reddit mention-velocity AND news polarity for the same ticker. The two are orthogonal axes — a ticker can be loud with neutral news (meme) or quiet with positive news (undiscovered upgrade). Combining catches both.

**Combo tool**: `fetch_attention_and_polarity`

**When to apply**: Always combine when the user asks about sentiment for a specific ticker. Either axis alone can mislead: pure social-sentiment misses the news direction; pure news polarity misses retail attention spikes.

### `regulatory_paper_trail` — *siblings*

**Kinds**: `sec_filings`, `insider`, `estimates`

SEC filings + insider transactions + analyst estimates. The paper trail behind a name: what management actually filed, what insiders actually bought/sold, what analysts actually project.

**When to apply**: When the user asks 'what's the actual regulatory paper trail for X' (often before earnings or after a news spike), pair these three. Insider transactions are a specific Form-4 subset of all filings — the wider sec_filings table catches 10-K / 10-Q / 8-K / etc.

### `event_calendar_overlay` — *primary_plus_context*

**Kinds**: `earnings_calendar`, `ipo_calendar`, `ohlcv`

Forward event calendars (earnings, IPOs) layered with the ticker's OHLCV chart. Tells the agent where the next catalysts are without leaving the price view.

**When to apply**: When the user asks 'what's coming up' or wants to position around an upcoming print, pair OHLCV with the relevant calendar. Earnings calendar for individual names; IPO calendar for sector-wide flow / new-listing impact.

### `shareholder_returns` — *siblings*

**Kinds**: `dividends`, `splits`

Dividends + splits give the full picture of cash + structural returns to shareholders over time. Dividends show the cash yield trajectory; splits show share-count history (relevant for adjusted-vs-raw price comparisons).

**When to apply**: When the user asks about a ticker's payout history or wants to understand a stock's return composition, create both as table cards. For a card-view preview, dividends is usually the headline; splits is a context table that's rarely the primary focus.

### `actuals_vs_estimates` — *primary_plus_context*

**Kinds**: `estimates`, `income`, `balance`, `cash`

Forward analyst estimates (revenue / EPS / EBITDA ranges) vs the historical fundamentals trio. Useful for 'is the company beating or missing'.

**When to apply**: Pair forward estimates (kind='estimates') with the most recent income statement when the user asks about consensus vs reality. Balance + cash become relevant when the question is about ability-to-deliver, not just earnings power.

### `analyst_consensus` — *orthogonal*

**Kinds**: `recommendation`, `sentiment`, `social_sentiment`

Monthly analyst recommendation counts (strong_buy / buy / hold / sell / strong_sell) plotted as a sentiment signal alongside news polarity and social attention.

**When to apply**: Analyst consensus shifts slowly but reliably. When recommendation trend is improving (more buy / fewer sell) but social_sentiment is loud-negative, you're watching a professional / retail divergence. Surface both alongside the news polarity for the fullest picture.

### `insider_ownership` — *orthogonal*

**Kinds**: `insider`, `insider_sentiment`, `sentiment`, `social_sentiment`

Insider transactions (Form-4 filings) + monthly MSPR + sentiment + social signals. Compare what insiders are DOING with what news / Reddit are SAYING. MSPR (kind='insider_sentiment') normalizes net buying/selling to [-1, +1]; insider (kind='insider') gives raw Form-4 transaction detail.

**When to apply**: Insiders selling into a news/social-sentiment spike is a classic divergence — the loudest convictions often coincide with the people closest to the data quietly cashing out. Use insider table alongside the attention+polarity combo for the fullest picture.

### `fundamentals_triplet` — *siblings*

**Kinds**: `income`, `balance`, `cash`

Income statement + balance sheet + cash flow for a ticker. Three views of the same firm's financials; none is complete alone. Income shows profitability, balance shows leverage / asset base, cash flow shows actual cash generation vs accounting profit.

**When to apply**: When the user asks for 'fundamentals' or 'how is company X doing financially', create three cards (one per kind) anchored on the same ticker + period. Comparing net income (income) against operating cash flow (cash) catches earnings quality issues that either statement alone hides.

### `price_in_context` — *primary_plus_context*

**Kinds**: `ohlcv`, `sentiment`, `social_sentiment`, `news`, `news_tone`

OHLCV anchored to either news polarity, social attention, or pattern annotations to give a price move its 'why'. Price tells you what happened; news/social/patterns tell you why.

**When to apply**: When the user asks 'why did X move' or 'what's behind this spike', pair the price chart with whichever context kind the data supports. For US equities/ETFs: sentiment + news. For meme tickers (MU, GME, TSLA): also social_sentiment. For crypto: social_sentiment + news + news_tone (GDELT topic-level tone for the broader narrative).

### `macro_mood_overlay` — *primary_plus_context*

**Kinds**: `news_tone`, `ohlcv`

GDELT topic-level tone time-series (news_tone) charted alongside an asset's OHLCV. Tone is article-level / macro-mood, NOT per-ticker — use for narrative reads ('how is the crypto coverage tone shifting?'), not per-stock signals.

**When to apply**: When the user asks about narrative shifts ('is bitcoin coverage turning sour?', 'how is AI-stock sentiment vs last month?'), pull a GDELT news_tone time-series against the asset OHLCV. Don't use this for per-ticker sentiment — GDELT tone is aggregated across all articles matching the query, so multi-ticker matches dilute the signal.

### `macro_with_asset` — *primary_plus_context*

**Kinds**: `macro`, `ohlcv`

A FRED macro series anchored alongside an asset's OHLCV to ask 'how does this asset respond to this macro driver?'. Rate-sensitive equities vs DGS10, gold vs M2SL, BTC vs DXY.

**When to apply**: When the user asks about a macro-thesis trade (e.g., 'how does gold do when real rates rise?'), pair the macro series with the asset OHLCV on the same x-axis. Use FRED's native frequency (often monthly or weekly) — don't try to interpolate to daily.

### `pattern_views` — *alternative_views*

**Kinds**: `ohlcv`

Same chart, two pattern-detection approaches: algorithmic (`detect_channels` / `detect_breakouts`) and vision (`detect_patterns_vision`). They have different blind spots — algo catches straight channels well, vision catches H&S / wedges / curved patterns better.

**When to apply**: When the user asks for pattern recognition on a chart, default to vision (per SKILL.md). Fall back to algorithmic if vision returns no high-confidence patterns. Don't run both unless the user wants a cross-check — they'll often annotate the same patterns and clutter the card.

### `forex_cross_source` — *alternative_views*

**Kinds**: `forex`

FX OHLC is served by yfinance, FMP, Tiingo, Polygon. They diverge in minor details (tick rounding, weekend handling). When precision matters, cross-check two sources on the same pair to validate the move.

**When to apply**: Normally just pick the primary (Tiingo). Use a second source only when validating a specific event (a flash move, a gap) where any source-specific artifact could mislead.

## 4. Multi-source coverage per kind

From `kind_coverage.py` — when more than one source serves the same kind, how they relate (primary / fallback / complementary) and the default routing chain.

### `crypto`

Crypto OHLCV — open/high/low/close/volume per bar. Binance is the primary path (full exchange-native data, no auth, ~2k spot pairs); FMP and Tiingo are fallbacks for when binance is rate-limited or doesn't list the pair.

| provider | tier | rate limit |
|---|---|---|
| `binance` | primary | 1200 request-weight/min/IP — effectively unlimited |
| `fmp` | fallback | 250 req/day on free tier — modest |
| `tiingo` | fallback | 1000 req/hr on free tier — generous |

**Default chain**: `binance` → `fmp` → `tiingo`

**Routing logic**: Binance first for any crypto request. When binance is rate-limited (HTTP 429 / weight exhausted) or the pair isn't listed, fall back to FMP, then Tiingo. The three agree closely on price but disagree on volume (binance = single-venue; FMP/Tiingo = composite). For volume-driven analysis, prefer binance.

### `social_sentiment`

Reddit-driven mention-velocity per ticker. NOT classical polarity sentiment (-1..1) — this is a count of how many times a ticker is being talked about right now vs. 24h ago. Best as a viral-attention signal that often precedes meme-driven moves. Pair with `kind='sentiment'` (AV/Marketaux) for actual polarity.

| provider | tier | rate limit |
|---|---|---|
| `apewisdom` | primary | no documented limit; cache intraday (5 min) |

**Default chain**: `apewisdom`

**Routing logic**: Apewisdom is the only free social-sentiment source we've kept after Stocktwits went Cloudflare-protected and Reddit PRAW app registration proved unreliable. For 'is anyone talking about X right now?' → apewisdom. For polarity of what's being said in news → kind='sentiment' (AV/Marketaux). The two are orthogonal — a ticker can be high-mention with neutral sentiment (mixed coverage) or low-mention with strong positive sentiment (analyst upgrade, no chatter yet).

### `sentiment`

Per-ticker news sentiment scores. Returned as a time-series DataFrame: each row is one article with timestamp = published_at, columns include sentiment_score (-1..1), relevance_score (0..1), title, url, article_source.

| provider | tier | rate limit |
|---|---|---|
| `alphavantage` | primary | 25 req/day, 5 req/min — TIGHT, cache aggressively |
| `marketaux` | fallback | 100 req/day, 1 req/sec — more generous than AV |
| `finnhub` | complementary | 60 req/min — generous |
| `gdelt` | article-level | Public, no auth, but ~83% reliability + flaky latency |

**Default chain**: `alphavantage` → `marketaux`

**Routing logic**: For per-ticker sentiment: try alphavantage first (best scoring quality, per-ticker granularity). If AV daily quota exhausted (error: 'Thank you for using Alpha Vantage! Our standard API rate limit is 25 requests per day'), fall back to marketaux (100 req/day). For richer signal: also pull finnhub insider-sentiment + recommendation as an ORTHOGONAL signal (insider activity vs news mood often diverges). GDELT tone is article-level only — use for general mood, NOT per-ticker.

