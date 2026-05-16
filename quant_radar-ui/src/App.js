import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { DashboardTabs } from "./components/DashboardTabs";
import { Sidebar } from "./components/Sidebar";
export default function App() {
    const [density, setDensity] = useState(2);
    const [refreshSec, setRefreshSec] = useState(5);
    return (_jsxs("div", { className: "h-full flex", children: [_jsx(Sidebar, { density: density, setDensity: setDensity, refreshSec: refreshSec, setRefreshSec: setRefreshSec }), _jsx("main", { className: "flex-1 flex flex-col", children: _jsx(DashboardTabs, { density: density, refreshSec: refreshSec }) })] }));
}
