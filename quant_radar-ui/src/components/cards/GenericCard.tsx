import type { Card } from "../../lib/types";

interface Props {
  card: Card;
}

// Fallback renderer for non-chart card types. Phase 14c replaces these
// with type-specific renderers (NewsCard, AnalysisCard, etc.).
export function GenericCard({ card }: Props) {
  return (
    <div className="border border-border rounded-lg bg-panel p-4 overflow-hidden">
      <div className="flex justify-between items-baseline mb-2">
        <h3 className="font-semibold">{card.title}</h3>
        <span className="text-xs text-muted">{card.type}</span>
      </div>
      {card.analysis_markdown ? (
        <div className="text-sm whitespace-pre-wrap">{card.analysis_markdown}</div>
      ) : card.news.length > 0 ? (
        <ul className="text-sm space-y-1">
          {card.news.slice(0, 8).map((it, i) => (
            <li key={i} className="truncate">
              {String(it.title ?? "")}{" "}
              <span className="text-muted">({String(it.source ?? "")})</span>
            </li>
          ))}
        </ul>
      ) : (
        <pre className="text-xs text-muted overflow-x-auto">
          {JSON.stringify(card, null, 2)}
        </pre>
      )}
    </div>
  );
}
