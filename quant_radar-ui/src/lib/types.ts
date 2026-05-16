// Mirrors quant_radar/server/schemas.py + quant_radar/cards/spec.py.
// Keep this file in sync with the FastAPI Pydantic models.

export type CardType = "chart" | "news" | "sentiment" | "analysis" | "combo";
export type Target = "main" | "working";

export type Interval =
  | "1m" | "5m" | "15m" | "1h" | "1d" | "1w" | "1mo";

export interface DataRef {
  source: string;
  kind: string;
  name: string;
  interval?: Interval;
  start?: string | null;
  end?: string | null;
}

export type AnnotationKind = "hline" | "vline" | "trendline" | "rect" | "text";

export interface Annotation {
  kind: AnnotationKind;
  points: [number, number][];
  label?: string | null;
  color?: string | null;
}

export interface ChartSpec {
  overlays: string[];
  subplots: string[];
  annotations: Annotation[];
}

export interface LayoutHint {
  width: number;
  height: number;
  x?: number | null;
  y?: number | null;
}

export interface Card {
  id: string;
  type: CardType;
  title: string;
  data_refs: DataRef[];
  chart_spec: ChartSpec | null;
  analysis_markdown: string | null;
  news: Record<string, unknown>[];
  layout: LayoutHint;
  created_at: string;
  updated_at: string;
}

export interface TimeSeriesResponse {
  source: string;
  kind: string;
  name: string;
  interval: string;
  timestamps: string[];
  columns: Record<string, number[]>;
}

export interface SourceCapability {
  name: string;
  kinds: string[];
  intervals: string[];
  history: string;
  coverage: string;
  auth: string;
  rate_limit: string;
  status: "active" | "limited" | "deferred" | "paid-only";
  notes?: string;
  examples?: string[];
}

export interface ProbeHistoryResponse {
  symbol: string;
  source: string;
  kind: string;
  first?: string;
  last?: string;
  bars: number;
}
