import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { HistoryPoint, Txn } from "../api/types";
import { buildChartRows, buildMarkers, type ChartRow, type Marker } from "../lib/chart";
import { compactCurrency, formatDate } from "../lib/format";

const AXIS = "hsl(153 9% 54%)";
const GRID = "hsl(150 24% 16%)";
const BUY = "hsl(145 63% 49%)";
const SELL = "hsl(6 53% 49%)";

interface MarkerGlyphProps {
  cx: number;
  cy: number;
  marker: Marker;
}

function MarkerGlyph({ cx, cy, marker }: MarkerGlyphProps) {
  const radius = marker.radius;
  const points =
    marker.action === "buy"
      ? `${cx},${cy - radius} ${cx - radius},${cy + radius * 0.7} ${cx + radius},${cy + radius * 0.7}`
      : `${cx},${cy + radius} ${cx - radius},${cy - radius * 0.7} ${cx + radius},${cy - radius * 0.7}`;
  return (
    <polygon
      data-testid="marker"
      data-date={marker.date}
      data-action={marker.action}
      data-value={marker.value}
      data-radius={radius.toFixed(3)}
      points={points}
      fill={marker.action === "buy" ? BUY : SELL}
      stroke="hsl(157 25% 10%)"
      strokeWidth={1}
    />
  );
}

interface TooltipContentProps {
  active?: boolean;
  payload?: { payload?: ChartRow }[];
}

function ChartTooltip({ active, payload }: TooltipContentProps) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  const marker = row.marker;
  return (
    <div className="rounded-lg border border-line bg-card px-3 py-2 text-xs shadow-tile">
      <p className="tnum text-fg">{formatDate(row.date)}</p>
      <p className="tnum mt-1 text-muted">Close ${row.close.toFixed(2)}</p>
      {marker ? (
        <p className={`tnum mt-1 ${marker.action === "buy" ? "text-buy" : "text-sell"}`}>
          <span aria-hidden="true">{marker.action === "buy" ? "▲" : "▼"}</span>{" "}
          {marker.action === "buy" ? "Buy" : "Sell"} {compactCurrency(marker.value)}
        </p>
      ) : null}
    </div>
  );
}

interface PriceChartProps {
  ticker: string | null;
  history: HistoryPoint[];
  txns: Txn[];
  loading: boolean;
}

export function PriceChart({ ticker, history, txns, loading }: PriceChartProps) {
  const markers = useMemo(() => buildMarkers(txns), [txns]);
  const rows = useMemo(() => buildChartRows(history, markers), [history, markers]);
  const maxMarker: Marker | undefined = markers.reduce<Marker | undefined>(
    (best, marker) => (!best || marker.value > best.value ? marker : best),
    undefined,
  );

  return (
    <section
      aria-label="Price and insider activity"
      data-testid="price-chart"
      data-markers={markers.length}
      data-history={history.length}
      className="panel flex h-[440px] flex-col"
    >
      <div className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <h2 className="font-display text-xl font-semibold">Price &amp; activity</h2>
          <p className="label mt-0.5">{ticker ?? "—"} · 6-month close</p>
        </div>
        <p className="text-xs text-muted">
          {markers.length === 0
            ? "No trades in window"
            : `Marker size ∝ value · largest ${maxMarker ? compactCurrency(maxMarker.value) : "—"}`}
        </p>
      </div>

      <div className="flex-1 px-2 pb-2 pt-3">
        {loading ? (
          <div className="skeleton m-3 h-[340px]" />
        ) : history.length === 0 ? (
          <p role="status" className="p-6 text-sm text-muted">
            No price history yet. Daily bars arrive after the next market close.
          </p>
        ) : (
          <div
            role="img"
            data-testid="chart-canvas"
            aria-label={`${ticker ?? "Ticker"} closing price over six months with ${markers.length} insider trade markers`}
            className="h-full w-full"
          >
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="date"
                  tickFormatter={(value: string) =>
                    new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric" })
                  }
                  stroke={AXIS}
                  tick={{ fontSize: 11 }}
                  minTickGap={40}
                  tickLine={false}
                />
                <YAxis
                  domain={["auto", "auto"]}
                  width={58}
                  orientation="right"
                  tickFormatter={(value: number) => `$${Math.round(value)}`}
                  stroke={AXIS}
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  content={(props: unknown) => (
                    <ChartTooltip {...(props as TooltipContentProps)} />
                  )}
                />
                <Line
                  type="monotone"
                  dataKey="close"
                  stroke="hsl(45 51% 70%)"
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
                {rows.map((row) => {
                  const marker = row.marker;
                  if (!marker) return null;
                  return (
                    <ReferenceDot
                      key={row.date}
                      x={row.date}
                      y={row.close}
                      r={0}
                      isFront
                      shape={(props: unknown) => {
                        const point = props as { cx?: number; cy?: number };
                        if (point.cx === undefined || point.cy === undefined) return <g />;
                        return <MarkerGlyph cx={point.cx} cy={point.cy} marker={marker} />;
                      }}
                    />
                  );
                })}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <p className="border-t border-line px-4 py-2 text-xs text-muted">
        ▲ open-market buys, ▼ open-market sells. One marker per date; the largest value is drawn.
        Awards and other codes are not plotted.
      </p>
    </section>
  );
}
