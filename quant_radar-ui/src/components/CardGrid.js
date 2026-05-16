import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useCards } from "../api/cards";
import { ChartCard } from "./cards/ChartCard";
import { GenericCard } from "./cards/GenericCard";
const EMPTY_MAIN = "Your main dashboard is empty. Saved cards from chat will appear here.";
const EMPTY_WORKING = "No working dashboard active. Ask the agent: " +
    '"Create a temporary working dashboard."';
export function CardGrid({ target, density, refreshSec }) {
    const { data: cards = [], isLoading, error } = useCards(target, refreshSec * 1000);
    if (isLoading)
        return _jsx("div", { className: "text-muted text-sm", children: "Loading cards\u2026" });
    if (error)
        return (_jsxs("div", { className: "rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300", children: ["Could not reach the API: ", String(error)] }));
    if (cards.length === 0)
        return (_jsx("div", { className: "rounded border border-border bg-panel p-4 text-sm text-muted", children: target === "main" ? EMPTY_MAIN : EMPTY_WORKING }));
    return (_jsx("div", { className: "grid gap-4", style: { gridTemplateColumns: `repeat(${density}, minmax(0, 1fr))` }, children: cards.map((c) => c.type === "chart" || c.type === "combo" ? (_jsx(ChartCard, { card: c }, c.id)) : (_jsx(GenericCard, { card: c }, c.id))) }));
}
