import type { Card } from "../../lib/types";

import { NewsCard } from "./NewsCard";

// Sentiment card = analysis_markdown (LLM summary) + optional news list.
// Closely related to AnalysisCard but renders headlines underneath when
// the agent attaches them.
export function SentimentCard({ card }: { card: Card }) {
  return (
    <div className="border border-border rounded-lg bg-panel p-4 h-full overflow-hidden flex flex-col gap-3">
      <div className="flex justify-between items-baseline">
        <h3 className="font-semibold">{card.title}</h3>
        <span className="text-xs text-muted">sentiment</span>
      </div>
      <div className="text-sm whitespace-pre-wrap leading-relaxed">
        {card.analysis_markdown ?? "_(no summary)_"}
      </div>
      {card.news.length > 0 && (
        <div className="mt-2 border-t border-border pt-2 -mx-1">
          <NewsCard card={card} />
        </div>
      )}
    </div>
  );
}
