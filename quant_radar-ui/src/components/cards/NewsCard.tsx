import type { Card } from "../../lib/types";

interface NewsItem {
  title?: string;
  url?: string;
  source?: string;
  published_at?: string;
  summary?: string;
}

export function NewsCard({ card }: { card: Card }) {
  const items = card.news as NewsItem[];
  return (
    <div className="border border-border rounded-lg bg-panel p-4 h-full overflow-hidden flex flex-col">
      <div className="flex justify-between items-baseline mb-2">
        <h3 className="font-semibold">{card.title}</h3>
        <span className="text-xs text-muted">{items.length} items</span>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-muted">No items.</p>
      ) : (
        <ul className="text-sm space-y-2 overflow-y-auto flex-1">
          {items.slice(0, 30).map((it, i) => (
            <li key={i} className="leading-snug">
              {it.url ? (
                <a
                  href={it.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-text hover:text-accent"
                >
                  {it.title ?? "(untitled)"}
                </a>
              ) : (
                <span>{it.title ?? "(untitled)"}</span>
              )}
              <div className="text-xs text-muted">
                {it.source ?? ""}
                {it.published_at ? ` · ${it.published_at}` : ""}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
