import { useQueryClient } from "@tanstack/react-query";
import { useState, type Dispatch, type SetStateAction } from "react";

import { useRefreshEpoch } from "../lib/refresh";

interface Props {
  density: number;
  setDensity: Dispatch<SetStateAction<number>>;
  terminalOpen: boolean;
  setTerminalOpen: Dispatch<SetStateAction<boolean>>;
}

export function Sidebar({
  density,
  setDensity,
  terminalOpen,
  setTerminalOpen,
}: Props) {
  const queryClient = useQueryClient();
  const { bump } = useRefreshEpoch();
  const [busy, setBusy] = useState(false);

  async function refreshNow() {
    setBusy(true);
    try {
      bump(); // future /api/data fetches add refresh=true for one cycle
      // Invalidate everything; refetches use the bumped epoch.
      await queryClient.invalidateQueries({ queryKey: ["cards"] });
      await queryClient.invalidateQueries({ queryKey: ["working-state"] });
      await queryClient.invalidateQueries({ queryKey: ["data"] });
    } finally {
      // Brief visual confirmation
      setTimeout(() => setBusy(false), 400);
    }
  }

  return (
    <aside className="w-64 shrink-0 border-r border-border bg-panel p-4 flex flex-col gap-6 overflow-y-auto">
      <div>
        <h1 className="text-xl font-bold tracking-tight">quant_radar</h1>
        <p className="text-xs text-muted mt-1">
          Read-only viewer. Cards come from your chat session.
        </p>
      </div>

      <button
        type="button"
        onClick={refreshNow}
        disabled={busy}
        className="rounded border border-border bg-bg hover:bg-border text-sm py-2 px-3 transition disabled:opacity-50"
        data-testid="refresh-now"
      >
        {busy ? "Refreshing…" : "↻ Refresh data"}
      </button>
      <p className="text-xs text-muted -mt-4">
        Card lists auto-poll every 5 s; click <em>Refresh</em> to also force
        a fresh pull from the upstream APIs (not just cache).
      </p>

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
          <code>make app</code> (ttyd on host).
        </p>
      </div>
    </aside>
  );
}
