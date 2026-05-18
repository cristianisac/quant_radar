import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { clearDashboard, useCards, useWorkingState } from "../api/cards";
import type { Card } from "../lib/types";

import { CardGrid } from "./CardGrid";

interface Props {
  density: number;
  onEnlarge: (card: Card) => void;
}

export function DashboardTabs({ density, onEnlarge }: Props) {
  const [active, setActive] = useState<"main" | "working">("main");
  const { data: workingState } = useWorkingState();
  const { data: mainCards = [] } = useCards("main");
  const { data: workingCards = [] } = useCards("working");
  const queryClient = useQueryClient();

  const tabs: { id: "main" | "working"; label: string }[] = [
    { id: "main", label: `Main (${mainCards.length})` },
  ];
  if (workingState?.is_open) {
    tabs.push({ id: "working", label: `Working (${workingCards.length})` });
  }

  const safeActive = tabs.some((t) => t.id === active) ? active : "main";
  const activeCount =
    safeActive === "main" ? mainCards.length : workingCards.length;

  async function handleClearAll() {
    if (activeCount === 0) return;
    const tabName = safeActive === "main" ? "Main" : "Working";
    if (
      !window.confirm(
        `Delete all ${activeCount} card${activeCount === 1 ? "" : "s"} from ${tabName}? This cannot be undone.`,
      )
    ) {
      return;
    }
    await clearDashboard(safeActive);
    await queryClient.invalidateQueries({ queryKey: ["cards", safeActive] });
  }

  return (
    <div className="flex-1 flex flex-col gap-3 p-4 overflow-hidden">
      <div className="flex items-center justify-between border-b border-border">
        <div className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setActive(t.id)}
              className={`px-3 py-2 text-sm border-b-2 -mb-px transition ${
                safeActive === t.id
                  ? "border-accent text-accent"
                  : "border-transparent text-muted hover:text-text"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        {activeCount > 0 && (
          <button
            type="button"
            onClick={handleClearAll}
            data-testid="clear-all-cards"
            title={`Delete all cards from ${safeActive === "main" ? "Main" : "Working"}`}
            className="text-xs text-muted hover:text-red-400 px-3 py-2 transition"
          >
            ✕ Clear all ({activeCount})
          </button>
        )}
      </div>
      <div className="flex-1 overflow-auto">
        <CardGrid target={safeActive} density={density} onEnlarge={onEnlarge} />
      </div>
    </div>
  );
}
