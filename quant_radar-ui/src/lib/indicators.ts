// Client-side indicator math — mirrors quant_radar/analytics/indicators.py.
// Computed in the browser so cards render without an extra round-trip
// after fetching the base time series.

function rollingMean(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i += 1) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    out.push(i >= period - 1 ? sum / period : null);
  }
  return out;
}

export function sma(values: number[], period: number): (number | null)[] {
  return rollingMean(values, period);
}

export function ema(values: number[], period: number): (number | null)[] {
  const alpha = 2 / (period + 1);
  const out: (number | null)[] = [];
  let prev: number | null = null;
  for (let i = 0; i < values.length; i += 1) {
    if (i < period - 1) {
      out.push(null);
      continue;
    }
    if (prev === null) {
      const slice = values.slice(0, period);
      prev = slice.reduce((a, b) => a + b, 0) / period;
    } else {
      prev = alpha * values[i] + (1 - alpha) * prev;
    }
    out.push(prev);
  }
  return out;
}

// Wilder's RSI — matches the Python adapter.
export function rsi(values: number[], period = 14): (number | null)[] {
  if (values.length < period + 1) return values.map(() => null);
  const out: (number | null)[] = new Array(values.length).fill(null);
  let gainSum = 0;
  let lossSum = 0;
  for (let i = 1; i <= period; i += 1) {
    const delta = values[i] - values[i - 1];
    if (delta >= 0) gainSum += delta;
    else lossSum -= delta;
  }
  let avgGain = gainSum / period;
  let avgLoss = lossSum / period;
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = period + 1; i < values.length; i += 1) {
    const delta = values[i] - values[i - 1];
    const gain = delta > 0 ? delta : 0;
    const loss = delta < 0 ? -delta : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

// Wilder's ATR.
export function atr(
  high: number[], low: number[], close: number[], period = 14,
): (number | null)[] {
  if (high.length < 2) return high.map(() => null);
  const tr: number[] = [0];
  for (let i = 1; i < high.length; i += 1) {
    const a = high[i] - low[i];
    const b = Math.abs(high[i] - close[i - 1]);
    const c = Math.abs(low[i] - close[i - 1]);
    tr.push(Math.max(a, b, c));
  }
  const out: (number | null)[] = new Array(tr.length).fill(null);
  if (tr.length < period + 1) return out;
  let prev = tr.slice(1, period + 1).reduce((a, b) => a + b, 0) / period;
  out[period] = prev;
  for (let i = period + 1; i < tr.length; i += 1) {
    prev = (prev * (period - 1) + tr[i]) / period;
    out[i] = prev;
  }
  return out;
}

// YoY % change — pct of close vs ~252 trading days back.
export function yoyPercent(values: number[], periods = 252): (number | null)[] {
  return values.map((v, i) =>
    i >= periods && values[i - periods] !== 0
      ? ((v - values[i - periods]) / values[i - periods]) * 100
      : null,
  );
}
