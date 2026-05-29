from quant_radar.tools.analytics import (
    analyze_indicators,
    analyze_moving_averages,
    compute_indicators,
    compute_returns,
    rolling_zscore,
)
from quant_radar.tools.compat import (
    all_analytical_tools,
    all_requirements,
    requirements_for,
    tools_for_ref,
)
from quant_radar.tools.dataframe import filter_by_date
from quant_radar.tools.etfs import (
    convert_bloomberg_to_yahoo,
    describe_etf_aum_coverage,
    etf_aum_scorecard,
    fetch_etf_aum,
)
from quant_radar.tools.governance import (
    request_user_decision,
    request_user_decision_yesno,
)
from quant_radar.tools.futures import (
    cme_futures_scorecard,
    describe_cme_futures_assets,
    fetch_cme_futures_volume,
)
from quant_radar.tools.calendar import (
    describe_economic_calendar_routing,
    fetch_economic_calendar,
)
from quant_radar.tools.cards import (
    add_annotation,
    clear_dashboard,
    close_working_dashboard,
    create_dashboard_card,
    load_dashboard,
    new_working_dashboard,
    persist_dashboard,
    remove_card,
    save_card_to_dashboard,
    update_card,
)
from quant_radar.tools.news import (
    fetch_news,
    fetch_top_headlines,
    score_sentiment,
    summarize_news,
)
from quant_radar.tools.sentiment import (
    describe_sentiment_routing,
    describe_social_sentiment_routing,
    fetch_attention_and_polarity,
    fetch_sentiment,
    fetch_social_sentiment,
)
from quant_radar.tools.patterns import (
    channel_annotations,
    detect_breakouts,
    detect_channels,
    detect_patterns_vision,
)
from quant_radar.tools.sources_meta import (
    describe_kind_coverage,
    describe_source,
    describe_symbol,
    list_all_symbols,
    list_binance_pairs,
    list_covered_kinds,
    list_kind_relationships,
    list_searchable_sources,
    list_sources,
    probe_history,
    relationships_for_kind,
    search_binance,
    search_fred,
    search_source,
    search_yfinance,
)

# --- Caveman timing wrapper ----------------------------------------------
#
# Every public tool gets wrapped with a perf_counter timer that emits a
# single line to stderr per call:
#
#     [timing] tool=fetch_etf_aum dur=4.823s
#
# Set ``QUANT_RADAR_TOOL_TIMING=0`` to silence. Default is on. This is the
# cheapest possible way to answer "where did those 12 minutes go?" — the
# user's chat log carries the line items, no profiler setup needed.
import os
import sys
import time
from functools import wraps

_TIMING_ENABLED = os.environ.get("QUANT_RADAR_TOOL_TIMING", "1") != "0"


def _timed(name: str, fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        t0 = time.perf_counter()
        try:
            return fn(*a, **kw)
        finally:
            sys.stderr.write(
                f"[timing] tool={name} dur={time.perf_counter() - t0:.3f}s\n"
            )
            sys.stderr.flush()

    return wrapper


__all__ = [
    "add_annotation",
    "all_analytical_tools",
    "all_requirements",
    "analyze_indicators",
    "analyze_moving_averages",
    "channel_annotations",
    "clear_dashboard",
    "cme_futures_scorecard",
    "convert_bloomberg_to_yahoo",
    "close_working_dashboard",
    "compute_indicators",
    "compute_returns",
    "create_dashboard_card",
    "describe_cme_futures_assets",
    "describe_economic_calendar_routing",
    "describe_etf_aum_coverage",
    "describe_kind_coverage",
    "describe_source",
    "describe_symbol",
    "detect_breakouts",
    "detect_channels",
    "detect_patterns_vision",
    "etf_aum_scorecard",
    "fetch_cme_futures_volume",
    "fetch_economic_calendar",
    "fetch_etf_aum",
    "fetch_news",
    "fetch_top_headlines",
    "filter_by_date",
    "list_all_symbols",
    "list_binance_pairs",
    "list_covered_kinds",
    "list_kind_relationships",
    "list_searchable_sources",
    "list_sources",
    "load_dashboard",
    "new_working_dashboard",
    "persist_dashboard",
    "probe_history",
    "relationships_for_kind",
    "request_user_decision",
    "request_user_decision_yesno",
    "remove_card",
    "requirements_for",
    "rolling_zscore",
    "save_card_to_dashboard",
    "describe_sentiment_routing",
    "describe_social_sentiment_routing",
    "fetch_attention_and_polarity",
    "fetch_sentiment",
    "fetch_social_sentiment",
    "score_sentiment",
    "search_binance",
    "search_fred",
    "search_source",
    "search_yfinance",
    "summarize_news",
    "tools_for_ref",
    "update_card",
]


if _TIMING_ENABLED:
    _g = globals()
    for _name in __all__:
        _fn = _g.get(_name)
        if callable(_fn):
            _g[_name] = _timed(_name, _fn)
    del _g, _name, _fn
