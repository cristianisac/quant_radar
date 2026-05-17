import { useState } from "react";

import { DashboardTabs } from "./components/DashboardTabs";
import { EnlargeModal } from "./components/EnlargeModal";
import { Sidebar } from "./components/Sidebar";
import { TerminalPanel } from "./components/TerminalPanel";
import { RefreshProvider } from "./lib/refresh";
import type { Card } from "./lib/types";

export default function App() {
  const [density, setDensity] = useState(2);
  const [terminalOpen, setTerminalOpen] = useState(false);
  const [enlarged, setEnlarged] = useState<Card | null>(null);

  return (
    <RefreshProvider>
      <div className="h-full flex">
        <Sidebar
          density={density}
          setDensity={setDensity}
          terminalOpen={terminalOpen}
          setTerminalOpen={setTerminalOpen}
        />
        <main className="flex-1 flex flex-col min-w-0">
          <DashboardTabs density={density} onEnlarge={setEnlarged} />
          <TerminalPanel
            visible={terminalOpen}
            onClose={() => setTerminalOpen(false)}
          />
        </main>
        <EnlargeModal card={enlarged} onClose={() => setEnlarged(null)} />
      </div>
    </RefreshProvider>
  );
}
