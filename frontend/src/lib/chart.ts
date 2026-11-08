import type { HistoryPoint, Txn } from "../api/types";

export interface Marker {
  date: string;
  action: "buy" | "sell";
  value: number;
  radius: number;
}

export interface ChartRow {
  date: string;
  close: number;
  buy: number | null;
  sell: number | null;
  marker: Marker | null;
}

/** UI-06: radius = 5 + 9 × √(value ÷ max value in window), in pixels. */
export function markerRadius(value: number, maxValue: number): number {
  if (!Number.isFinite(value) || value <= 0 || maxValue <= 0) return 5;
  return 5 + 9 * Math.sqrt(value / maxValue);
}

/** One marker per trading date; the largest open-market value wins (UI-06). */
export function buildMarkers(txns: Txn[]): Marker[] {
  const byDate = new Map<string, Txn>();
  for (const txn of txns) {
    if (txn.action === "other" || txn.value === null || txn.value <= 0) continue;
    const current = byDate.get(txn.date);
    if (!current || (current.value ?? 0) < txn.value) byDate.set(txn.date, txn);
  }

  const chosen = [...byDate.values()];
  const maxValue = chosen.reduce((max, txn) => Math.max(max, txn.value ?? 0), 0);

  return chosen.map((txn) => ({
    date: txn.date,
    action: txn.action === "sell" ? "sell" : "buy",
    value: txn.value ?? 0,
    radius: markerRadius(txn.value ?? 0, maxValue),
  }));
}

export function buildChartRows(history: HistoryPoint[], markers: Marker[]): ChartRow[] {
  const byDate = new Map(markers.map((marker) => [marker.date, marker]));
  return history.map((point) => {
    const marker = byDate.get(point.date) ?? null;
    return {
      date: point.date,
      close: point.close,
      buy: marker?.action === "buy" ? point.close : null,
      sell: marker?.action === "sell" ? point.close : null,
      marker,
    };
  });
}

export function markerCount(rows: ChartRow[]): number {
  return rows.filter((row) => row.marker !== null).length;
}
