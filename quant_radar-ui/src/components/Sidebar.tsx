import type { Dispatch, SetStateAction } from "react";

interface Props {
  density: number;
  setDensity: Dispatch<SetStateAction<number>>;
  refreshSec: number;
  setRefreshSec: Dispatch<SetStateAction<number>>;
  terminalOpen: boolean;
  setTerminalOpen: Dispatch<SetStateAction<boolean>>;
}

export function Sidebar({
  density,
  setDensity,
  refreshSec,
  setRefreshSec,
  terminalOpen,
  setTerminalOpen,
}: Props) {
  return (
    <aside className="w-64 shrink-0 border-r border-border bg-panel p-4 flex flex-col gap-6 overflow-y-auto">
      <div>
        <h1 className="text-xl font-bold tracking-tight">quant_radar</h1>
        <p className="text-xs text-muted mt-1">
          Read-only viewer. Cards come from your chat session.
        </p>
      </div>

      <label className="block">
        <div className="flex justify-between text-sm mb-1">
          <span>Cards per row</span>
          <span className="text-accent">{density}</span>
        </div>
        <input
          type="range"
          min={1}
          max={4}
          value={density}
          onChange={(e) => setDensity(Number(e.target.value))}
          className="w-full accent-accent"
        />
      </label>

      <label className="block">
        <div className="flex justify-between text-sm mb-1">
          <span>Auto-refresh (seconds)</span>
          <span className="text-accent">{refreshSec}</span>
        </div>
        <input
          type="range"
          min={2}
          max={30}
          value={refreshSec}
          onChange={(e) => setRefreshSec(Number(e.target.value))}
          className="w-full accent-accent"
        />
      </label>

      <div className="border-t border-border pt-4">
        <h2 className="text-sm font-semibold mb-2">Terminal</h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={terminalOpen}
            onChange={(e) => setTerminalOpen(e.target.checked)}
            className="accent-accent"
          />
          Show terminal
        </label>
        <p className="text-xs text-muted mt-2">
          Drag the top edge of the panel to resize. Requires{" "}
          <code>make dev</code> (ttyd on host).
        </p>
      </div>
    </aside>
  );
}
