import Plotly from "plotly.js-dist-min";
import { useEffect, useMemo, useRef, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";

import { useDataRef } from "../../api/data";
import { atr, ema, rsi, sma, yoyPercent } from "../../lib/indicators";
import type { Annotation, Card, TimeSeriesResponse } from "../../lib/types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Plot = createPlotlyComponent(Plotly) as any;

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
  const ref = card.data_refs[0] ?? null;
  const { data, isLoading, error } = useDataRef(ref);
  // Drop useResizeHandler in favor of an explicit ResizeObserver. Plotly's
  // internal resize watcher loses races inside react-grid-layout's
  // absolute-positioned cells; reading the bounding rect ourselves is
  // more reliable.
  const containerRef = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState({ width: 0, height: 0 });
  useEffect(() => {
    if (!containerRef.current) return;
    const obs = new ResizeObserver(([entry]) => {
      const r = entry.contentRect;
      if (r.width > 0 && r.height > 0) {
        setMeasured({ width: r.width, height: r.height });
      }
    });
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);
  const width = measured.width || 600;
  const height = forcedHeight ?? (measured.height || 320);

  const figure = useMemo(
    () => buildFigure(data ?? null, card, width, height),
    [data, card, width, height],
  );

  return (
    <div className="border border-border rounded-lg bg-panel p-3 h-full overflow-hidden flex flex-col">
      <div className="flex justify-between items-baseline mb-2 shrink-0">
        <h3 className="font-semibold">{card.title}</h3>
        <span className="text-xs text-muted">{ref?.name ?? "(no data)"}</span>
      </div>
      <div
        ref={containerRef}
        className="flex-1 min-h-[200px] relative"
      >
        {isLoading && (
          <div className="text-xs text-muted">Loading data…</div>
        )}
        {error && (
          <div className="text-xs text-red-400">
            {String((error as Error).message)}
          </div>
        )}
        {data && figure && (
          <Plot
            data={figure.traces}
            layout={figure.layout}
            config={{
              displayModeBar: enlarged,
              modeBarButtonsToAdd: enlarged
                ? ["drawline", "drawopenpath", "drawrect", "eraseshape"]
                : [],
              scrollZoom: enlarged,
              responsive: false,
            }}
          />
        )}
      </div>
    </div>
  );
}

function buildFigure(
  data: TimeSeriesResponse | null,
  card: Card,
  width: number,
  height: number,
): { traces: object[]; layout: object } | null {
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

  if (isOhlcv) {
    traces.push({
      type: "candlestick", x,
      open: cols.open, high: cols.high, low: cols.low, close: cols.close,
      increasing: { line: { color: "#22c55e" } },
      decreasing: { line: { color: "#ef4444" } },
      name: data.name, xaxis: "x", yaxis: "y",
    });
  } else {
    traces.push({
      type: "scatter", mode: "lines", x, y: close,
      line: { color: "#22c55e", width: 1.5 },
      name: data.name, xaxis: "x", yaxis: "y",
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
    traces.push({
      type: sub === "volume" ? "bar" : "scatter",
      mode: sub === "volume" ? undefined : "lines",
      x, y,
      name: sub.toUpperCase(),
      xaxis: "x", yaxis: yAxis,
      line: sub === "volume" ? undefined : { width: 1 },
      marker: sub === "volume" ? { color: "#64748b" } : undefined,
    });
    subplotRow += 1;
  }

  const layout: Record<string, unknown> = {
    width, height,
    autosize: false,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#fafafa", size: 11 },
    margin: { l: 50, r: 20, t: 10, b: 40 },
    showlegend: false,
    xaxis: {
      gridcolor: "#262730",
      rangeslider: { visible: false },
      anchor: nRows > 1 ? `y${nRows}` : "y",
    },
    shapes,
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
        title: { text: subplots[i].toUpperCase(), font: { size: 10 } },
      };
    }
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
