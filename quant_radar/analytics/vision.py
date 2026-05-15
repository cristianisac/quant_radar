"""Render a chart to PNG for visual pattern analysis.

The output is meant to be opened by the calling agent (Claude Code) with
its Read tool — Claude is multimodal so it can interpret the image
directly. No external SDK / API key is needed; we reuse the agent's own
vision.

Charts are saved under ``data/cache/vision/`` so the directory is
gitignored along with the rest of the cache.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive backend; safe inside Docker
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from quant_radar.core.config import paths  # noqa: E402


def _vision_dir() -> Path:
    d = paths.cache / "vision"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)


def render_chart_png(
    df: pd.DataFrame,
    *,
    asset_name: str,
    title: str | None = None,
    out_path: Path | None = None,
    width_px: int = 1400,
    height_px: int = 800,
) -> Path:
    """Render an OHLC or close-only frame to a PNG file and return the path."""
    if len(df) == 0:
        raise ValueError("cannot render an empty DataFrame")

    fig, ax = plt.subplots(figsize=(width_px / 100, height_px / 100), dpi=100)

    is_ohlcv = {"open", "high", "low", "close"}.issubset(df.columns)
    if is_ohlcv:
        x = mdates.date2num(df.index.to_numpy())
        up = df["close"].to_numpy() >= df["open"].to_numpy()
        colors: list[str] = ["tab:green" if u else "tab:red" for u in up]
        ax.vlines(x, df["low"].to_numpy(), df["high"].to_numpy(),
                  colors=colors, linewidth=0.6)
        ax.vlines(x, df["open"].to_numpy(), df["close"].to_numpy(),
                  colors=colors, linewidth=2.0)
        ax.xaxis_date()
    else:
        col = "close" if "close" in df.columns else df.columns[0]
        ax.plot(df.index.to_numpy(), df[col].to_numpy(), color="tab:blue", linewidth=1.0)

    ax.set_title(title or f"{asset_name}")
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("date")
    ax.set_ylabel("price")
    fig.autofmt_xdate()
    fig.tight_layout()

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    path = out_path or _vision_dir() / f"{_safe_name(asset_name)}_{stamp}.png"
    fig.savefig(path)
    plt.close(fig)
    return path
