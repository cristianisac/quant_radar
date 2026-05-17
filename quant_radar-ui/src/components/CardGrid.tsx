import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import GridLayoutLib, { WidthProvider, type Layout } from "react-grid-layout";

import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import { deleteCard, saveCardToMain, useCards } from "../api/cards";
import type { Card, Target } from "../lib/types";

import { AnalysisCard } from "./cards/AnalysisCard";
import { ChartCard } from "./cards/ChartCard";
import { NewsCard } from "./cards/NewsCard";
import { SentimentCard } from "./cards/SentimentCard";

// Diagnostic wrapper: catches errors from any card renderer so a
// single bad card doesn't take down the entire dashboard.
import { Component, type ReactNode } from "react";
class CardErrorBoundary extends Component<
  { children: ReactNode; title: string },
  { error: Error | null }
> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error) {
    console.error(`[CardErrorBoundary] ${this.props.title}:`, error);
  }
  render() {
    if (this.state.error) {
      return (
        <div className="border border-red-500/40 bg-red-500/10 rounded-lg p-4 text-sm text-red-300">
          <strong>{this.props.title}</strong>: {String(this.state.error.message)}
        </div>
      );
    }
    return this.props.children;
  }
}

const ResponsiveGrid = WidthProvider(GridLayoutLib);

const EMPTY_MAIN =
  "Your main dashboard is empty. Saved cards from chat will appear here.";
const EMPTY_WORKING =
  "No working dashboard active. Ask the agent: " +
  '"Create a temporary working dashboard."';

interface Props {
  target: Target;
  density: number;
  onEnlarge: (card: Card) => void;
}

function renderCard(card: Card) {
  let inner;
  switch (card.type) {
    case "chart":
    case "combo":
      inner = <ChartCard card={card} />;
      break;
    case "news":
      inner = <NewsCard card={card} />;
      break;
    case "sentiment":
      inner = <SentimentCard card={card} />;
      break;
    case "analysis":
      inner = <AnalysisCard card={card} />;
      break;
    default:
      inner = <AnalysisCard card={card} />;
  }
  return <CardErrorBoundary title={card.title}>{inner}</CardErrorBoundary>;
}

// 12-column grid à la Bootstrap. Density is approximate "cards per row";
// width per card = floor(12 / density).
function defaultLayout(cards: Card[], density: number): Layout[] {
  const colsPerCard = Math.max(1, Math.floor(12 / density));
  const rowH = 6;
  return cards.map((c, i) => {
    const col = (i % density) * colsPerCard;
    const row = Math.floor(i / density) * rowH;
    return {
      i: c.id,
      x: c.layout.x ?? col,
      y: c.layout.y ?? row,
      w: c.layout.width ?? colsPerCard,
      h: c.layout.height ?? rowH,
      minW: 2,
      minH: 3,
    };
  });
}

export function CardGrid({ target, density, onEnlarge }: Props) {
  const { data: cards = [], isLoading, error } = useCards(target);
  const [layout, setLayout] = useState<Layout[]>([]);
  const queryClient = useQueryClient();

  const baseLayout = useMemo(() => defaultLayout(cards, density), [cards, density]);

  useEffect(() => {
    setLayout(baseLayout);
  }, [baseLayout]);

  async function handleSave(card: Card) {
    await saveCardToMain(card.id);
    queryClient.invalidateQueries({ queryKey: ["cards", "main"] });
  }

  async function handleDelete(card: Card) {
    if (!window.confirm(`Delete "${card.title}" from ${target}?`)) return;
    await deleteCard(card.id, target);
    queryClient.invalidateQueries({ queryKey: ["cards", target] });
  }

  if (isLoading) return <div className="text-muted text-sm">Loading cards…</div>;
  if (error)
    return (
      <div className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
        Could not reach the API: {String((error as Error).message)}
      </div>
    );
  if (cards.length === 0)
    return (
      <div className="rounded border border-border bg-panel p-4 text-sm text-muted">
        {target === "main" ? EMPTY_MAIN : EMPTY_WORKING}
      </div>
    );

  return (
    <ResponsiveGrid
      className="layout"
      layout={layout}
      cols={12}
      rowHeight={40}
      isDraggable
      isResizable
      draggableHandle=".drag-handle"
      onLayoutChange={setLayout}
      compactType="vertical"
    >
      {cards.map((c) => (
        <div key={c.id} className="relative">
          <div className="drag-handle absolute top-1 left-1 px-1 text-xs text-muted cursor-move select-none z-10">
            ⠿
          </div>
          <div className="absolute top-1 right-1 flex gap-2 text-xs z-10">
            {target === "working" && (
              <button
                type="button"
                onClick={() => handleSave(c)}
                className="text-muted hover:text-accent"
                title="Save to main"
                data-testid="save-card"
              >
                ★
              </button>
            )}
            <button
              type="button"
              onClick={() => handleDelete(c)}
              className="text-muted hover:text-red-400"
              title={`Delete from ${target}`}
              data-testid="delete-card"
            >
              ✕
            </button>
            <button
              type="button"
              onClick={() => onEnlarge(c)}
              className="text-muted hover:text-accent"
              title="Enlarge"
              data-testid="enlarge-card"
            >
              ⛶
            </button>
          </div>
          {renderCard(c)}
        </div>
      ))}
    </ResponsiveGrid>
  );
}
