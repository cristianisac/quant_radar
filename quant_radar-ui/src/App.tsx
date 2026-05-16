import { useState } from "react";

import { DashboardTabs } from "./components/DashboardTabs";
import { Sidebar } from "./components/Sidebar";

export default function App() {
  const [density, setDensity] = useState(2);
  const [refreshSec, setRefreshSec] = useState(5);

  return (
    <div className="h-full flex">
      <Sidebar
        density={density}
        setDensity={setDensity}
        refreshSec={refreshSec}
        setRefreshSec={setRefreshSec}
      />
      <main className="flex-1 flex flex-col">
        <DashboardTabs density={density} refreshSec={refreshSec} />
      </main>
    </div>
  );
}
