import { useMemo, useState } from "react";

import { useDataRef } from "../../api/data";
import { friendlyName } from "../../lib/labels";
import type { Card } from "../../lib/types";

interface Props {
  card: Card;
  enlarged?: boolean;
}

// Currency / large-number formatter for financial values.
function formatCell(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "string") return v;
  if (typeof v !== "number" || !Number.isFinite(v)) return String(v);
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(2)}k`;
  if (abs >= 1) return `${sign}${abs.toFixed(2)}`;
  if (abs > 0) return `${sign}${abs.toFixed(4)}`;
  return "0";
}

// Periods are the timestamps (rows in our DataFrame contract). We want
// the most recent first in the table.
function formatPeriod(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toISOString().slice(0, 10);
}

// For the compact card preview: which columns are the "headline" metrics
// we'd put in front. Falls back to the first 3 numeric columns if no
// preferred fields are present.
const PREFERRED_HEADLINE: Record<string, string[]> = {
  income: ["revenue", "gross_profit", "bottom_line_net_income", "diluted_earnings_per_share"],
  balance: ["total_assets", "total_liabilities", "total_debt", "cash_and_cash_equivalents"],
  cash: ["operating_cash_flow", "free_cash_flow"],
  sentiment: ["sentiment_score", "relevance_score", "sentiment_label", "title"],
  social_sentiment: ["mentions", "mentions_change_pct", "rank", "name"],
  dividends: ["amount", "dividend_yield", "frequency", "payment_date"],
  splits: ["numerator", "denominator", "splitType"],
  estimates: ["estimated_revenue_avg", "estimated_eps_avg", "estimated_ebitda_avg", "number_analysts_eps"],
  insider: ["transaction_price", "share", "transaction_code", "insider_name"],
  earnings_calendar: ["symbol", "eps_estimate", "revenue_estimate", "hour"],
  ipo_calendar: ["symbol", "company_name", "exchange", "price"],
  recommendation: ["strong_buy", "buy", "hold", "sell", "strong_sell"],
  insider_sentiment: ["mspr", "change", "symbol"],
  sec_filings: ["report_type", "report_url", "accepted_date"],
  ticker_news: ["title", "publisher", "sentiment", "keywords"],
  options_chain: ["contract_type", "strike_price", "contract_ticker", "primary_exchange"],
  economic_calendar: ["event", "actual", "consensus", "previous"],
  futures_aggregate: ["standard_contracts", "micro_contracts", "total_notional", "active_months_std"],
  etf_aum: ["yahoo", "aum", "nav", "longname"],
};

function pickHeadlineCols(kind: string, allCols: string[]): string[] {
  const preferred = PREFERRED_HEADLINE[kind] ?? [];
  const matched = preferred.filter((c) => allCols.includes(c));
  if (matched.length > 0) return matched.slice(0, 4);
  // Fallback: first 4 columns that look numeric (skip meta strings).
  const skip = new Set([
    "symbol", "cik", "reported_currency", "fiscal_period", "fiscal_year",
    "filing_date", "accepted_date", "calendar_year",
  ]);
  return allCols.filter((c) => !skip.has(c)).slice(0, 4);
}

export function TableCard({ card, enlarged = false }: Props) {
  const ref = card.data_refs[0] ?? null;
  const { data, isLoading, error } = useDataRef(ref);
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(false);

  const rows = useMemo(() => {
    if (!data || data.timestamps.length === 0) return [];
    const periodCount = data.timestamps.length;
    const r: Array<Record<string, unknown>> = [];
    for (let i = 0; i < periodCount; i += 1) {
      const row: Record<string, unknown> = { _period: data.timestamps[i] };
      for (const [col, vals] of Object.entries(data.columns)) {
        row[col] = vals[i];
      }
      r.push(row);
    }
    // Most-recent first by default — that's how financial statements
    // are typically read.
    r.reverse();
    return r;
  }, [data]);

  const allCols = useMemo(
    () => (data ? Object.keys(data.columns) : []),
    [data],
  );

  const compactCols = useMemo(
    () => pickHeadlineCols(ref?.kind ?? "", allCols),
    [allCols, ref],
  );

  const visibleRows = useMemo(() => {
    if (!sortCol) return rows;
    const sorted = [...rows];
    sorted.sort((a, b) => {
      const av = a[sortCol] as number | string | null;
      const bv = b[sortCol] as number | string | null;
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return sortAsc ? av - bv : bv - av;
      }
      return sortAsc
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
    return sorted;
  }, [rows, sortCol, sortAsc]);

  function toggleSort(col: string) {
    if (sortCol === col) setSortAsc((a) => !a);
    else {
      setSortCol(col);
      setSortAsc(false);
    }
  }

  const badge =
    (ref?.name ? `${ref.name} ${ref.kind === "income" ? "income statement" : ref.kind === "balance" ? "balance sheet" : ref.kind === "cash" ? "cash flow" : ref.kind}` : "")
    || "(no data)";
  const friendly = friendlyName(ref?.name ?? "");

  if (isLoading) {
    return (
      <div className="border border-border rounded-lg bg-panel p-3 h-full flex flex-col">
        <div className="flex justify-between items-baseline mb-1 shrink-0">
          <h3 className="font-semibold">{card.title}</h3>
          <span className="text-xs text-muted">{badge}</span>
        </div>
        <div className="text-xs text-muted">Loading…</div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="border border-border rounded-lg bg-panel p-3 h-full flex flex-col">
        <div className="text-xs text-red-400">
          {String((error as Error).message)}
        </div>
      </div>
    );
  }

  // Compact preview: every row, but only the headline columns; the
  // tbody container is overflow-auto so the card scrolls vertically.
  // Previously we sliced to 4 rows here, which hid the rest of a 10-
  // row scorecard (user, 2026-05-29). Enlarged: every row + every
  // column, sortable.
  const previewRows = visibleRows;
  const previewCols = enlarged ? allCols : compactCols;

  return (
    <div className="border border-border rounded-lg bg-panel p-3 h-full flex flex-col overflow-hidden">
      <div className="flex justify-between items-baseline mb-1 shrink-0">
        <h3 className="font-semibold">{card.title}</h3>
        <span className="text-xs text-muted">{badge}</span>
      </div>
      {friendly && (
        <div className="text-xs text-muted mb-2 shrink-0">{friendly}</div>
      )}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs font-mono">
          <thead className="text-left text-muted sticky top-0 bg-panel">
            <tr>
              <th className="py-1 pr-3 cursor-pointer hover:text-text"
                  onClick={() => toggleSort("_period")}>
                Period {sortCol === "_period" ? (sortAsc ? "▲" : "▼") : ""}
              </th>
              {previewCols.map((c) => (
                <th key={c}
                    className="py-1 pr-3 text-right cursor-pointer hover:text-text"
                    onClick={() => toggleSort(c)}
                    title={c}>
                  {c.replace(/_/g, " ")}
                  {sortCol === c ? (sortAsc ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {previewRows.map((row, i) => (
              <tr key={i} className="border-t border-border/30">
                <td className="py-1 pr-3 text-muted">
                  {formatPeriod(row._period as string)}
                </td>
                {previewCols.map((c) => (
                  <td key={c} className="py-1 pr-3 text-right">
                    {formatCell(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
