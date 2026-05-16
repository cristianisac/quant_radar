import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import Plotly from "plotly.js-dist-min";
import createPlotlyComponent from "react-plotly.js/factory";
import { useDataRef } from "../../api/data";
const Plot = createPlotlyComponent(Plotly);
// Minimal Plotly renderer — Phase 14b proves the pipeline (DataRef →
// HTTP → Plotly figure). Phase 14c adds overlays, subplots, candlestick
// rendering, and persisted annotations.
export function ChartCard({ card }) {
    const ref = card.data_refs[0] ?? null;
    const { data, isLoading, error } = useDataRef(ref);
    return (_jsxs("div", { className: "border border-border rounded-lg bg-panel p-3 overflow-hidden", children: [_jsxs("div", { className: "flex justify-between items-baseline mb-2", children: [_jsx("h3", { className: "font-semibold", children: card.title }), _jsx("span", { className: "text-xs text-muted", children: ref?.name ?? "(no data_ref)" })] }), isLoading && _jsx("div", { className: "text-xs text-muted", children: "Loading data\u2026" }), error && (_jsxs("div", { className: "text-xs text-red-400", children: ["Could not load: ", String(error)] })), data && (_jsx(Plot, { data: [
                    {
                        x: data.timestamps,
                        y: data.columns.close ?? data.columns.value ?? [],
                        type: "scatter",
                        mode: "lines",
                        line: { color: "#22c55e", width: 1.5 },
                        name: ref?.name ?? "",
                    },
                ], layout: {
                    paper_bgcolor: "rgba(0,0,0,0)",
                    plot_bgcolor: "rgba(0,0,0,0)",
                    font: { color: "#fafafa" },
                    margin: { l: 50, r: 20, t: 10, b: 40 },
                    height: 320,
                    xaxis: { gridcolor: "#262730" },
                    yaxis: { gridcolor: "#262730" },
                    showlegend: false,
                }, config: { displayModeBar: false, responsive: true }, style: { width: "100%" }, useResizeHandler: true }))] }));
}
