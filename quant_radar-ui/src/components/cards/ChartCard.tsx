import Plotly from "plotly.js-dist-min";
import createPlotlyComponent from "react-plotly.js/factory";

import { useDataRef } from "../../api/data";
import type { Card } from "../../lib/types";

const Plot = createPlotlyComponent(Plotly);

interface Props {
  card: Card;
}

// Minimal Plotly renderer — Phase 14b proves the pipeline (DataRef →
// HTTP → Plotly figure). Phase 14c adds overlays, subplots, candlestick
// rendering, and persisted annotations.
export function ChartCard({ card }: Props) {
  const ref = card.data_refs[0] ?? null;
  const { data, isLoading, error } = useDataRef(ref);

  return (
    <div className="border border-border rounded-lg bg-panel p-3 overflow-hidden">
      <div className="flex justify-between items-baseline mb-2">
        <h3 className="font-semibold">{card.title}</h3>
        <span className="text-xs text-muted">{ref?.name ?? "(no data_ref)"}</span>
      </div>

      {isLoading && <div className="text-xs text-muted">Loading data…</div>}
      {error && (
        <div className="text-xs text-red-400">Could not load: {String(error)}</div>
      )}
      {data && (
        <Plot
          data={[
            {
              x: data.timestamps,
              y: data.columns.close ?? data.columns.value ?? [],
              type: "scatter",
              mode: "lines",
              line: { color: "#22c55e", width: 1.5 },
              name: ref?.name ?? "",
            },
          ]}
          layout={{
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            font: { color: "#fafafa" },
            margin: { l: 50, r: 20, t: 10, b: 40 },
            height: 320,
            xaxis: { gridcolor: "#262730" },
            yaxis: { gridcolor: "#262730" },
            showlegend: false,
          }}
          config={{ displayModeBar: false, responsive: true }}
          style={{ width: "100%" }}
          useResizeHandler
        />
      )}
    </div>
  );
}
