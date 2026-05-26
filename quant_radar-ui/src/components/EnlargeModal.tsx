import { useEffect } from "react";
import { createPortal } from "react-dom";

import type { Card } from "../lib/types";

import { AnalysisCard } from "./cards/AnalysisCard";
import { ChartCard } from "./cards/ChartCard";
import { NewsCard } from "./cards/NewsCard";
import { SentimentCard } from "./cards/SentimentCard";
import { TableCard } from "./cards/TableCard";

interface Props {
  card: Card | null;
  onClose: () => void;
}

export function EnlargeModal({ card, onClose }: Props) {
  useEffect(() => {
    if (!card) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [card, onClose]);

  if (!card) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 bg-bg flex items-stretch"
      onClick={onClose}
    >
      <div
        className="bg-bg w-screen h-screen flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center px-4 py-2 border-b border-border">
          <h2 className="font-semibold">{card.title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-muted hover:text-text text-sm"
          >
            ✕ close (Esc)
          </button>
        </div>
        <div className="flex-1 overflow-hidden p-4 min-h-0">
          {(card.type === "chart" || card.type === "combo") && (
            <ChartCard card={card} enlarged />
          )}
          {card.type === "news" && <NewsCard card={card} />}
          {card.type === "sentiment" && <SentimentCard card={card} />}
          {card.type === "analysis" && <AnalysisCard card={card} />}
          {card.type === "table" && <TableCard card={card} enlarged />}
        </div>
        {(card.type === "chart" || card.type === "combo") && (
          <div className="px-4 py-2 border-t border-border text-xs text-muted">
            ⚠️ Drawings in the toolbar are visual-only. To persist a shape,
            ask the agent to call <code>add_annotation</code>.
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
