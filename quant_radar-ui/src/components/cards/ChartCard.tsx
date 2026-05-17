import Plotly from "plotly.js-dist-min";
import { useEffect, useMemo, useRef } from "react";

import { useDataRef } from "../../api/data";
import { atr, ema, rsi, sma, yoyPercent } from "../../lib/indicators";
import { labelFor, subplotLabel } from "../../lib/labels";
import type { Annotation, Card, TimeSeriesResponse } from "../../lib/types";

/* eslint-disable @typescript-eslint/no-explicit-any */
const Plotly_ = Plotly as any;

const OVERLAY_FN: Record<string, (close: number[]) => (number | null)[]> = {
  sma_50: (c) => sma(c, 50),
  sma_200: (c) => sma(c, 200),
  ema_12: (c) => ema(c, 12),
  ema_26: (c) => ema(c, 26),
};

const OVERLAY_COLOR: Record<string, string> = {
  sma_50: "#22c55e",
  sma_200: "#ef4444",
  ema_12: "#3b82f6",
  ema_26: "#a855f7",
};

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

  const figure = useMemo(
    () => buildFigure([data0 ?? null, data1 ?? null], card),
    [data0, data1, card],
  );

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
      <div className="flex justify-between items-baseline mb-2 shrink-0">
        <h3 className="font-semibold">{card.title}</h3>
        <span className="text-xs text-muted">{badge}</span>
      </div>
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
): { traces: object[]; layout: object } | null {
  const data = datas[0];
  if (!data || data.timestamps.length === 0) return null;
  const cols = data.columns;
  const x = data.timestamps;
  const close = cols.close ?? cols.value ?? [];
  const isOhlcv = ["open", "high", "low", "close"].every((k) => k in cols);
  const spec = card.chart_spec;

  const subplots = (spec?.subplots ?? []).filter((s) =>
    isSupportedSubplot(s, cols),
  );
  const nRows = 1 + subplots.length;
  const traces: object[] = [];

  const primaryName = labelFor(data.name);
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
    const close2 = cols2.close ?? cols2.value ?? [];
    traces.push({
      type: "scatter", mode: "lines",
      x: second.timestamps, y: close2,
      line: { color: "#fbbf24", width: 1.5 },
      name: labelFor(second.name),
      xaxis: "x",
      yaxis: `y${secondAxisIndex}`,
      showlegend: true,
    });
  }

  for (const overlay of spec?.overlays ?? []) {
    const fn = OVERLAY_FN[overlay];
    if (!fn) continue;
    traces.push({
      type: "scatter", mode: "lines", x, y: fn(close),
      line: { color: OVERLAY_COLOR[overlay] ?? "#fbbf24", width: 1 },
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
    font: { color: "#fafafa", size: 11 },
    // Top margin holds the legend so it doesn't sit on the price panel.
    margin: { l: 50, r: 20, t: 28, b: 40 },
    showlegend: true,
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
