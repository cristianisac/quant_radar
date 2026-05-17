// Human-friendly labels for common symbols. The /api/data response only
// carries the raw ticker (e.g. "DGS10"); this dictionary lets the UI add
// the long form ("10y Treasury Yield") in card badges and legends.
const FRIENDLY: Record<string, string> = {
  // FRED macro
  DGS10: "10y Treasury Yield",
  DGS2: "2y Treasury Yield",
  DGS30: "30y Treasury Yield",
  CPIAUCSL: "CPI (All Urban Consumers)",
  UNRATE: "US Unemployment Rate",
  FEDFUNDS: "Federal Funds Rate",
  GDP: "US GDP",
  M2SL: "M2 Money Supply",
  DEXUSEU: "USD/EUR FX Rate",
  T10Y2Y: "10y–2y Yield Spread",
  // Equities indices
  "^GSPC": "S&P 500",
  "^IXIC": "Nasdaq Composite",
  "^DJI": "Dow Jones Industrial",
  "^VIX": "VIX",
  // Crypto majors
  "BTC-USD": "Bitcoin",
  "ETH-USD": "Ethereum",
  BTCUSDT: "Bitcoin (Binance)",
  ETHUSDT: "Ethereum (Binance)",
  SOLUSDT: "Solana (Binance)",
};

export function friendlyName(symbol: string | undefined | null): string | null {
  if (!symbol) return null;
  return FRIENDLY[symbol] ?? null;
}

// "DGS10 — 10y Treasury Yield" when a friendly name is known; raw symbol otherwise.
export function labelFor(symbol: string | undefined | null): string {
  if (!symbol) return "";
  const friendly = friendlyName(symbol);
  return friendly ? `${symbol} — ${friendly}` : symbol;
}

const SUBPLOT_LABELS: Record<string, string> = {
  rsi: "RSI (14)",
  atr: "ATR (14)",
  volume: "Volume",
  yoy: "YoY %",
};

export function subplotLabel(kind: string): string {
  return SUBPLOT_LABELS[kind] ?? kind.toUpperCase();
}
