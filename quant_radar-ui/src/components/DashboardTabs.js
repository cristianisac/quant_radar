import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { useWorkingState, useCards } from "../api/cards";
import { CardGrid } from "./CardGrid";
export function DashboardTabs({ density, refreshSec }) {
    const [active, setActive] = useState("main");
    const refreshMs = refreshSec * 1000;
    const { data: workingState } = useWorkingState(refreshMs);
    const { data: mainCards = [] } = useCards("main", refreshMs);
    const { data: workingCards = [] } = useCards("working", refreshMs);
    const tabs = [
        { id: "main", label: `Main (${mainCards.length})` },
    ];
    if (workingState?.is_open) {
        tabs.push({ id: "working", label: `Working (${workingCards.length})` });
    }
    // Keep "working" selectable only when the working tab is visible.
    const safeActive = tabs.some((t) => t.id === active) ? active : "main";
    return (_jsxs("div", { className: "flex-1 flex flex-col gap-3 p-4 overflow-hidden", children: [_jsx("div", { className: "flex gap-1 border-b border-border", children: tabs.map((t) => (_jsx("button", { type: "button", onClick: () => setActive(t.id), className: `px-3 py-2 text-sm border-b-2 -mb-px transition ${safeActive === t.id
                        ? "border-accent text-accent"
                        : "border-transparent text-muted hover:text-text"}`, children: t.label }, t.id))) }), _jsx("div", { className: "flex-1 overflow-auto", children: _jsx(CardGrid, { target: safeActive, density: density, refreshSec: refreshSec }) })] }));
}
