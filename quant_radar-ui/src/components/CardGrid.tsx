import { useCards } from "../api/cards";
import type { Target } from "../lib/types";

import { ChartCard } from "./cards/ChartCard";
import { GenericCard } from "./cards/GenericCard";

interface Props {
  target: Target;
  density: number;
  refreshSec: number;
}

const EMPTY_MAIN =
  "Your main dashboard is empty. Saved cards from chat will appear here.";
const EMPTY_WORKING =
  "No working dashboard active. Ask the agent: " +
  '"Create a temporary working dashboard."';

export function CardGrid({ target, density, refreshSec }: Props) {
  const { data: cards = [], isLoading, error } = useCards(target, refreshSec * 1000);

  if (isLoading) return <div className="text-muted text-sm">Loading cards…</div>;
  if (error)
    return (
      <div className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
        Could not reach the API: {String(error)}
      </div>
    );
  if (cards.length === 0)
    return (
      <div className="rounded border border-border bg-panel p-4 text-sm text-muted">
        {target === "main" ? EMPTY_MAIN : EMPTY_WORKING}
      </div>
    );

  return (
    <div
      className="grid gap-4"
      style={{ gridTemplateColumns: `repeat(${density}, minmax(0, 1fr))` }}
    >
      {cards.map((c) =>
        c.type === "chart" || c.type === "combo" ? (
          <ChartCard key={c.id} card={c} />
        ) : (
          <GenericCard key={c.id} card={c} />
        ),
      )}
    </div>
  );
}
