import type { Card } from "../../lib/types";

export function AnalysisCard({ card }: { card: Card }) {
  return (
    <div className="border border-border rounded-lg bg-panel p-4 h-full overflow-hidden flex flex-col">
      <div className="flex justify-between items-baseline mb-2">
        <h3 className="font-semibold">{card.title}</h3>
        <span className="text-xs text-muted">{card.type}</span>
      </div>
      <div className="text-sm whitespace-pre-wrap leading-relaxed overflow-y-auto flex-1">
        {card.analysis_markdown ?? "_(empty)_"}
      </div>
    </div>
  );
}
