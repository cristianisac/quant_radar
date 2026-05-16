"""Streamlit viewer.

Renders the Main and Working dashboards from disk. The viewer is
**read-only** — it does not create or modify cards. The chat agent
(Claude Code) writes cards to disk via ``quant_radar.tools``; this app
polls disk and refreshes when files change.

Run with ``make docker-ui``.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from quant_radar.cards import Card, store
from quant_radar.cards.spec import Target
from quant_radar.ui.data import hydrate
from quant_radar.ui.render import build_chart_figure, chart_modebar_config


def _page_config() -> None:
    st.set_page_config(
        page_title="quant_radar",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def _sidebar() -> tuple[int, int, bool, int]:
    st.sidebar.title("quant_radar")
    st.sidebar.caption("Read-only viewer. Cards come from your chat session.")
    density = st.sidebar.slider(
        "Cards per row", min_value=1, max_value=4, value=2,
        help="More columns = smaller cards. Zoom out for high density.",
    )
    refresh_sec = st.sidebar.slider(
        "Auto-refresh (seconds)", min_value=2, max_value=30, value=5,
    )

    st.sidebar.divider()
    st.sidebar.subheader("Terminal")
    show_terminal = st.sidebar.toggle(
        "Show terminal",
        value=False,
        help=(
            "Embed a Claude Code shell at the bottom of the page. "
            "Requires `make app` (not `make docker-ui`) — that launcher "
            "spawns ttyd on 127.0.0.1:7681."
        ),
    )
    terminal_height = st.sidebar.slider(
        "Terminal height (px)",
        min_value=240, max_value=900, value=420, step=20,
        disabled=not show_terminal,
    )

    if st.sidebar.button("Reload now"):
        st.rerun()
    return density, refresh_sec, show_terminal, terminal_height


TTYD_URL = "http://localhost:7681"


def _render_terminal_panel(height: int) -> None:
    """Embed the host's ttyd-backed Claude Code shell as a bottom panel."""
    st.divider()
    cols = st.columns([6, 1])
    cols[0].markdown("**Claude Code terminal**")
    cols[1].markdown(
        f"<a href='{TTYD_URL}' target='_blank' style='float:right'>open in new tab ↗</a>",
        unsafe_allow_html=True,
    )
    st.iframe(TTYD_URL, height=height)
    st.caption(
        "Loopback-only via ttyd on 127.0.0.1:7681. **Blank panel?** "
        "You probably started with `make docker-ui` — that's viewer-only. "
        "Use `make app` instead to launch ttyd alongside Streamlit."
    )


def _hydrate_card_frames(card: Card) -> list[pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    for ref in card.data_refs:
        try:
            frames.append(hydrate(ref))
        except Exception as e:  # noqa: BLE001
            st.warning(f"Could not hydrate {ref.name}: {e}")
    return frames


def _render_card_body(card: Card, *, enlarged: bool) -> None:
    if card.type == "analysis":
        st.markdown(card.analysis_markdown or "_(no content)_")
        return
    if card.type == "news":
        if not card.news:
            st.info("No news items.")
            return
        for item in card.news:
            title = item.get("title", "(no title)")
            url = item.get("url", "")
            src = item.get("source", "")
            ts = item.get("published_at", "")
            if url:
                st.markdown(f"- [{title}]({url}) — *{src}* · {ts}")
            else:
                st.markdown(f"- {title} — *{src}* · {ts}")
        return
    if card.type == "sentiment":
        summary = card.analysis_markdown or "_(no summary)_"
        st.markdown(summary)
        return
    if card.type in ("chart", "combo"):
        if not card.data_refs or card.chart_spec is None:
            st.info("Chart card has no data_refs or chart_spec.")
            return
        frames = _hydrate_card_frames(card)
        if not frames or len(frames[0]) == 0:
            st.warning("No data available for this card yet.")
            return
        fig = build_chart_figure(card, frames, show_modebar=enlarged)
        st.plotly_chart(
            fig,
            use_container_width=True,
            config=chart_modebar_config(drawing_enabled=enlarged),
        )
        return
    st.warning(f"Unknown card type: {card.type}")


@st.dialog("Enlarged card", width="large")
def _enlarge_dialog(card_id: str, target: Target) -> None:
    card = store.get(card_id, target)
    if card is None:
        st.error("Card not found.")
        return
    st.subheader(card.title)
    _render_card_body(card, enlarged=True)
    if card.type in ("chart", "combo"):
        st.warning(
            "⚠️ **Drawings here are visual only — they disappear on refresh.** "
            "To persist a shape, copy its coordinates and ask the agent to call "
            "`add_annotation(card_id, ...)`."
        )


def _render_dashboard(cards: list[Card], target: Target, density: int) -> None:
    if not cards:
        if target == "working":
            st.info(
                "No working dashboard active. Ask the agent: "
                "*\"Create a temporary working dashboard.\"*"
            )
        else:
            st.info(
                "Your main dashboard is empty. Saved cards from chat will appear here."
            )
        return
    cols = st.columns(density)
    for i, card in enumerate(cards):
        col = cols[i % density]
        with col, st.container(border=True):
            head_cols = st.columns([4, 1])
            head_cols[0].markdown(f"**{card.title}**")
            if head_cols[1].button("⛶", key=f"big-{target}-{card.id}", help="Enlarge"):
                _enlarge_dialog(str(card.id), target)
            _render_card_body(card, enlarged=False)
            st.caption(f"`{card.type}` · id: `{str(card.id)[:8]}`")


def main() -> None:
    _page_config()
    density, refresh_sec, show_terminal, terminal_height = _sidebar()
    st_autorefresh(interval=refresh_sec * 1000, key="dashboard-refresh")

    main_cards = store.list_cards("main")
    working_open = store.working_is_open()
    working_cards = store.list_cards("working") if working_open else []

    tab_labels = [f"Main ({len(main_cards)})"]
    if working_open:
        tab_labels.append(f"Working ({len(working_cards)})")
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        _render_dashboard(main_cards, "main", density)
    if working_open:
        with tabs[1]:
            _render_dashboard(working_cards, "working", density)

    if show_terminal:
        _render_terminal_panel(terminal_height)


if __name__ == "__main__":
    main()
