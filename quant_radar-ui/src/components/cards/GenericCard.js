import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
// Fallback renderer for non-chart card types. Phase 14c replaces these
// with type-specific renderers (NewsCard, AnalysisCard, etc.).
export function GenericCard({ card }) {
    return (_jsxs("div", { className: "border border-border rounded-lg bg-panel p-4 overflow-hidden", children: [_jsxs("div", { className: "flex justify-between items-baseline mb-2", children: [_jsx("h3", { className: "font-semibold", children: card.title }), _jsx("span", { className: "text-xs text-muted", children: card.type })] }), card.analysis_markdown ? (_jsx("div", { className: "text-sm whitespace-pre-wrap", children: card.analysis_markdown })) : card.news.length > 0 ? (_jsx("ul", { className: "text-sm space-y-1", children: card.news.slice(0, 8).map((it, i) => (_jsxs("li", { className: "truncate", children: [String(it.title ?? ""), " ", _jsxs("span", { className: "text-muted", children: ["(", String(it.source ?? ""), ")"] })] }, i))) })) : (_jsx("pre", { className: "text-xs text-muted overflow-x-auto", children: JSON.stringify(card, null, 2) }))] }));
}
