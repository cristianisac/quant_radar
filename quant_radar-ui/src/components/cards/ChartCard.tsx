import Plotly from "plotly.js-dist-min";
import { useEffect, useMemo, useRef } from "react";

import { useDataRef } from "../../api/data";
import { atr, ema, rsi, sma, yoyPercent } from "../../lib/indicators";
import { friendlyName, subplotLabel } from "../../lib/labels";
import type { Annotation, Card, TimeSeriesResponse } from "../../lib/types";

/* eslint-disable @typescript-eslint/no-explicit-any */
const Plotly_ = Plotly as any;

// Parametric overlay resolution: any sma_<N> or ema_<N> works without
// editing a hardcoded dictionary. The agent can ask for sma_137 or
// ema_500 and the chart renders it — no rebuild, no code change.
const OVERLAY_RE = /^(sma|ema)_(\d+)$/;

// Column-agnostic price-series picker. Mirrors the Python rule
// (CLAUDE.md): close → value → first numeric column. Used so single-
// column frames like GDELT `news_tone` render as a line chart without
// any frontend code edit.
function pickFirstNumericColumn(
  cols: Record<string, (number | string | null)[]>,
): (number | null)[] | null {
  for (const k of Object.keys(cols)) {
    const arr = cols[k] ?? [];
    let sawNum = false;
    for (const v of arr) {
      if (typeof v === "number" && Number.isFinite(v)) {
        sawNum = true;
        break;
      }
    }
    if (sawNum) {
      return arr.map((v) =>
        typeof v === "number" && Number.isFinite(v) ? v : null,
      );
    }
  }
  return null;
}

function overlayFn(name: string): ((close: number[]) => (number | null)[]) | null {
  const m = OVERLAY_RE.exec(name);
  if (!m) return null;
  const period = parseInt(m[2], 10);
  if (!Number.isFinite(period) || period < 2) return null;
  return m[1] === "sma" ? (c) => sma(c, period) : (c) => ema(c, period);
}

// Stable hashed colour so the same overlay name keeps the same colour
// across renders without us curating a per-period palette. 8 well-
// separated dark-bg hues; deterministic mapping from the overlay name.
const OVERLAY_PALETTE = [
  "#22c55e", // green
  "#ef4444", // red
  "#3b82f6", // blue
  "#a855f7", // purple
  "#14b8a6", // teal
  "#f43f5e", // pink
  "#f97316", // orange
  "#facc15", // yellow
];

function overlayColor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i += 1) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return OVERLAY_PALETTE[h % OVERLAY_PALETTE.length];
}

interface Props {
  card: Card;
  height?: number;
  enlarged?: boolean;
}

export function ChartCard({ card, height: forcedHeight, enlarged = false }: Props) {
  const ref0 = card.data_refs[0] ?? null;
  const ref1 = card.data_refs[1] ?? null;
  const { data: data0, isLoading: loading0, error } = useDataRef(ref0);
  const { data: data1, isLoading: loading1 } = useDataRef(ref1);
  const elRef = useRef<HTMLDivElement>(null);
  const isLoading = loading0 || loading1;

  // Compact = card view. Drop subplots and tighten margins so the price
  // chart actually fills the small card. Enlarged view gets everything.
  const compact = !enlarged;

  const figure = useMemo(
    () => buildFigure([data0 ?? null, data1 ?? null], card, { compact }),
    [data0, data1, card, compact],
  );

  // At-a-glance stat strip: latest close + 1d/5d/30d/90d % change,
  // colour-coded. Lets the user see "is this card flashing red or
  // green right now?" without enlarging.
  const stats = useMemo(() => computeQuickStats(data0 ?? null), [data0]);

  // Call Plotly directly. react-plotly.js's auto-init failed silently
  // inside react-grid-layout cells; controlling the lifecycle here
  // makes failures loud. ResizeObserver triggers Plot.resize when the
  // grid cell changes size.
  useEffect(() => {
    const el = elRef.current;
    if (!el || !figure) return;
    Plotly_
      .newPlot(el, figure.traces, figure.layout, {
        displayModeBar: enlarged,
        modeBarButtonsToAdd: enlarged
          ? ["drawline", "drawopenpath", "drawrect", "eraseshape"]
          : [],
        // Trim verbose default buttons so the vertical modebar stays short.
        modeBarButtonsToRemove: [
          "lasso2d",
          "select2d",
          "toggleSpikelines",
          "hoverClosestCartesian",
          "hoverCompareCartesian",
        ],
        scrollZoom: enlarged,
        responsive: true,
        displaylogo: false,
      })
      .catch((e: unknown) =>
        console.error("[ChartCard] Plotly.newPlot failed:", e),
      );
    const obs = new ResizeObserver(() => {
      Plotly_.Plots.resize(el);
    });
    obs.observe(el);
    return () => {
      obs.disconnect();
      Plotly_.purge(el);
    };
  }, [figure, enlarged]);

  const wrapperStyle = forcedHeight
    ? { height: forcedHeight }
    : { height: "100%", minHeight: 240 };

  // Keep the corner badge short — the legend below already spells out
  // the friendly long-form for each series.
  const badge = [ref0?.name, ref1?.name].filter(Boolean).join(" · ") || "(no data)";

  return (
    <div className="border border-border rounded-lg bg-panel p-3 h-full overflow-hidden flex flex-col">
      <div className="flex justify-between items-baseline mb-1 shrink-0">
        <h3 className="font-semibold">{card.title}</h3>
        <span className="text-xs text-muted">{badge}</span>
      </div>
      {stats && (
        <div className="flex items-baseline gap-3 mb-1 text-xs shrink-0">
          <span className="font-mono font-semibold text-sm text-text">
            {formatValue(stats.last)}
          </span>
          {(["1d", "5d", "30d", "90d", "1y"] as const).map((p) =>
            stats.changes[p] !== null ? (
              <span
                key={p}
                className={
                  stats.changes[p]! >= 0 ? "text-green-400" : "text-red-400"
                }
              >
                {stats.changes[p]! >= 0 ? "▲" : "▼"}{" "}
                {Math.abs(stats.changes[p]! * 100).toFixed(2)}%{" "}
                <span className="text-muted">{p}</span>
              </span>
            ) : null,
          )}
        </div>
      )}
      <div
        className="qr-chart-host flex-1 min-h-0 relative"
        style={wrapperStyle}
      >
        {isLoading && <div className="text-xs text-muted">Loading data…</div>}
        {error && (
          <div className="text-xs text-red-400">
            {String((error as Error).message)}
          </div>
        )}
        <div ref={elRef} style={{ width: "100%", height: "100%" }} />
      </div>
    </div>
  );
}

function buildFigure(
  datas: (TimeSeriesResponse | null)[],
  card: Card,
  opts: { compact?: boolean } = {},
): { traces: object[]; layout: object } | null {
  const data = datas[0];
  if (!data || data.timestamps.length === 0) return null;
  const cols = data.columns;
  const x = data.timestamps;
  // Column-agnostic waterfall — matches CLAUDE.md's Python-side rule:
  // close → value → first numeric column. Lets a single-column frame
  // like GDELT's `tone` render without code edit.
  const close = cols.close ?? cols.value ?? pickFirstNumericColumn(cols) ?? [];
  const isOhlcv = ["open", "high", "low", "close"].every((k) => k in cols);
  const spec = card.chart_spec;

  // Compact = card view: skip subplots, hide legend (we have the stat
  // strip + title), tighter margins. Enlarged keeps everything.
  const compact = !!opts.compact;
  const subplots = compact
    ? []
    : (spec?.subplots ?? []).filter((s) => isSupportedSubplot(s, cols));
  const nRows = 1 + subplots.length;
  const traces: object[] = [];

  const primaryName = pickLabel(data.name, data.display_name);
  if (isOhlcv) {
    traces.push({
      type: "candlestick", x,
      open: cols.open, high: cols.high, low: cols.low, close: cols.close,
      increasing: { line: { color: "#22c55e" } },
      decreasing: { line: { color: "#ef4444" } },
      name: primaryName, xaxis: "x", yaxis: "y",
      showlegend: true,
    });
  } else {
    traces.push({
      type: "scatter", mode: "lines", x, y: close,
      line: { color: "#22c55e", width: 1.5 },
      name: primaryName, xaxis: "x", yaxis: "y",
      showlegend: true,
    });
  }

  const second = datas[1];
  const hasSecond = second !== null && second !== undefined && second.timestamps.length > 0;
  // Secondary y-axis is placed after all subplot axes, so naming doesn't
  // collide. nRows already accounts for the main row + subplots.
  const secondAxisIndex = nRows + 1;
  if (hasSecond) {
    const cols2 = second.columns;
    const close2 = cols2.close ?? cols2.value ?? pickFirstNumericColumn(cols2) ?? [];
    const secondName = pickLabel(second.name, second.display_name);
    traces.push({
      type: "scatter", mode: "lines",
      x: second.timestamps, y: close2,
      line: { color: "#fbbf24", width: 1.5 },
      name: secondName,
      xaxis: "x",
      yaxis: `y${secondAxisIndex}`,
      showlegend: true,
    });
  }

  for (const overlay of spec?.overlays ?? []) {
    const fn = overlayFn(overlay);
    if (!fn) continue;
    traces.push({
      type: "scatter", mode: "lines", x, y: fn(close),
      line: { color: overlayColor(overlay), width: 1 },
      name: overlay, xaxis: "x", yaxis: "y",
    });
  }

  const shapes: object[] = [];
  for (const ann of spec?.annotations ?? []) {
    addAnnotationToFigure(ann, traces, shapes);
  }

  let subplotRow = 2;
  for (const sub of subplots) {
    const yAxis = `y${subplotRow}`;
    let y: (number | null)[] = [];
    if (sub === "rsi") y = rsi(close);
    else if (sub === "atr") y = atr(cols.high ?? [], cols.low ?? [], close);
    else if (sub === "volume") y = cols.volume ?? [];
    else if (sub === "yoy") y = yoyPercent(close);
    const label = subplotLabel(sub);
    if (sub === "volume") {
      traces.push({
        type: "bar", x, y,
        name: label,
        xaxis: "x", yaxis: yAxis,
        marker: { color: "#64748b" },
        showlegend: false,
      });
    } else {
      traces.push({
        type: "scatter", mode: "lines", x, y,
        name: label,
        xaxis: "x", yaxis: yAxis,
        line: { width: 1 },
        showlegend: false,
      });
    }
    subplotRow += 1;
  }

  // Subplot title overlays — one per extra row. Anchored to the top-left
  // of each subplot's y-axis domain so the label sits inside the panel
  // even after window resizes.
  const subplotAnnotations: object[] = [];

  const layout: Record<string, unknown> = {
    autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#fafafa", size: compact ? 9 : 11 },
    // Compact: tight margins, no legend (the JSX stat strip carries
    // the trace name visually). Enlarged: room for Plotly's legend.
    margin: compact
      ? { l: 40, r: 8, t: 4, b: 22 }
      : { l: 50, r: 20, t: 28, b: 40 },
    showlegend: !compact,
    legend: {
      orientation: "h",
      yanchor: "bottom", y: 1.02,
      xanchor: "left", x: 0,
      bgcolor: "rgba(0,0,0,0)",
      font: { size: 10 },
    },
    xaxis: {
      gridcolor: "#262730",
      // Candlestick traces auto-enable rangeslider; force off when
      // we have subplots since the slider doesn't play nicely with
      // multi-axis layouts.
      rangeslider: { visible: false },
      anchor: nRows > 1 ? `y${nRows}` : "y",
    },
    shapes,
    // Modebar lives in the paper margin, away from the data. Compact
    // vertical so it tucks against the top-right border.
    modebar: {
      orientation: "v",
      bgcolor: "rgba(0,0,0,0)",
      color: "#71717a",
      activecolor: "#fbbf24",
    },
  };
  const priceDomain: [number, number] = nRows === 1 ? [0, 1] : [0.42, 1];
  layout.yaxis = { domain: priceDomain, gridcolor: "#262730" };
  if (nRows > 1) {
    const subHeight = 0.4 / subplots.length;
    for (let i = 0; i < subplots.length; i += 1) {
      const top = 0.4 - i * subHeight;
      const bottom = top - subHeight + 0.02;
      layout[`yaxis${i + 2}`] = {
        domain: [Math.max(0, bottom), top],
        gridcolor: "#262730",
      };
      subplotAnnotations.push({
        text: subplotLabel(subplots[i]),
        xref: "paper", yref: "paper",
        x: 0.005, y: top,
        xanchor: "left", yanchor: "top",
        showarrow: false,
        font: { size: 10, color: "#a1a1aa" },
        bgcolor: "rgba(28,31,38,0.6)",
        borderpad: 2,
      });
    }
  }
  layout.annotations = subplotAnnotations;
  if (hasSecond) {
    // Right-side y-axis overlaying the price panel — different scale,
    // so the second series stays readable when its magnitude differs
    // wildly from the first (e.g. treasury yield vs crypto price).
    layout[`yaxis${secondAxisIndex}`] = {
      overlaying: "y",
      side: "right",
      domain: priceDomain,
      gridcolor: "transparent",
      tickfont: { color: "#fbbf24" },
    };
    layout.margin = { l: 50, r: 50, t: 10, b: 40 };
  }
  return { traces, layout };
}

// Label priority: curated dictionary (most concise) → server display_name
// (e.g. FRED API title, accurate but verbose) → raw symbol. Each tier is
// a fallback for the next, so unknown FRED codes still get a real title.
function pickLabel(symbol: string, serverDisplayName?: string | null): string {
  const curated = friendlyName(symbol);
  if (curated) return `${symbol} — ${curated}`;
  if (serverDisplayName) return `${symbol} — ${serverDisplayName}`;
  return symbol;
}

function isSupportedSubplot(s: string, cols: Record<string, number[]>): boolean {
  if (s === "rsi" || s === "yoy") return "close" in cols || "value" in cols;
  if (s === "atr") return "high" in cols && "low" in cols && "close" in cols;
  if (s === "volume") return "volume" in cols;
  return false;
}

function addAnnotationToFigure(
  ann: Annotation, traces: object[], shapes: object[],
): void {
  if (ann.kind === "hline" && ann.points.length > 0) {
    shapes.push({
      type: "line", x0: 0, x1: 1, xref: "paper",
      y0: ann.points[0][1], y1: ann.points[0][1],
      line: { color: ann.color ?? "#fafafa", dash: "dash", width: 1 },
    });
  } else if (ann.kind === "vline" && ann.points.length > 0) {
    shapes.push({
      type: "line", x0: ann.points[0][0], x1: ann.points[0][0],
      y0: 0, y1: 1, yref: "paper",
      line: { color: ann.color ?? "#fafafa", dash: "dash", width: 1 },
    });
  } else if (ann.kind === "trendline" && ann.points.length >= 2) {
    traces.push({
      type: "scatter", mode: "lines",
      x: ann.points.map((p) => new Date(p[0] * 1000)),
      y: ann.points.map((p) => p[1]),
      line: { color: ann.color ?? "#fafafa", dash: "dash", width: 1 },
      name: ann.label ?? "trendline",
      xaxis: "x", yaxis: "y",
    });
  } else if (ann.kind === "rect" && ann.points.length >= 2) {
    shapes.push({
      type: "rect",
      x0: ann.points[0][0], x1: ann.points[1][0],
      y0: ann.points[0][1], y1: ann.points[1][1],
      line: { color: ann.color ?? "#fafafa" },
      fillcolor: "rgba(255,255,255,0.05)",
    });
  }
}

// --- At-a-glance stats for the card-view header strip ---
//
// Returns latest close + percent-change over the last 1d / 5d / 30d /
// 90d / 1y so the user can see "is this card flashing red or green
// now?" without enlarging. Uses *calendar-day* windows (not bar count)
// via timestamp lookup, so the labels stay honest across data
// frequencies — e.g. "1y" on a monthly FRED series correctly picks
// the bar from 365 days back, not 12 bars (which would be a year)
// or 252 bars (which would be 21 years).

type Period = "1d" | "5d" | "30d" | "90d" | "1y";

interface QuickStats {
  last: number;
  changes: Record<Period, number | null>;
}

const PERIOD_DAYS: Record<Period, number> = {
  "1d": 1,
  "5d": 5,
  "30d": 30,
  "90d": 90,
  "1y": 365,
};

const DAY_MS = 86_400_000;

function indexNDaysBack(
  timestamps: string[], lastIdx: number, days: number,
): number {
  const target = new Date(timestamps[lastIdx]).getTime() - days * DAY_MS;
  // Linear scan backwards; data is monotonic-by-timestamp by contract,
  // and series are at most ~16k points (FRED DGS10 daily since 1962).
  for (let i = lastIdx - 1; i >= 0; i -= 1) {
    if (new Date(timestamps[i]).getTime() <= target) return i;
  }
  return -1;
}

function computeQuickStats(data: TimeSeriesResponse | null): QuickStats | null {
  if (!data || data.timestamps.length === 0) return null;
  const cols = data.columns;
  const series = cols.close ?? cols.value ?? null;
  if (!series || series.length === 0) return null;
  // Pull the last finite value as "now".
  let lastIdx = series.length - 1;
  while (lastIdx >= 0 && !Number.isFinite(series[lastIdx])) lastIdx -= 1;
  if (lastIdx < 0) return null;
  const last = series[lastIdx];
  const changes: Record<Period, number | null> = {
    "1d": null, "5d": null, "30d": null, "90d": null, "1y": null,
  };
  for (const [p, days] of Object.entries(PERIOD_DAYS) as [Period, number][]) {
    const refIdx = indexNDaysBack(data.timestamps, lastIdx, days);
    if (refIdx < 0) continue;
    const ref = series[refIdx];
    if (!Number.isFinite(ref) || ref === 0) continue;
    changes[p] = (last - ref) / ref;
  }
  return { last, changes };
}

function formatValue(v: number): string {
  if (!Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (abs >= 10_000) return `${(v / 1_000).toFixed(2)}k`;
  if (abs >= 100) return v.toFixed(2);
  if (abs >= 1) return v.toFixed(3);
  if (abs >= 0.01) return v.toFixed(4);
  return v.toExponential(2);
}
