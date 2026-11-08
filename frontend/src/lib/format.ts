const UNITS = [
  { limit: 1e12, suffix: "T" },
  { limit: 1e9, suffix: "B" },
  { limit: 1e6, suffix: "M" },
  { limit: 1e3, suffix: "K" },
] as const;

export function compactCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value < 0 ? "-" : "";
  return `${sign}${formatMagnitude(Math.abs(value))}`;
}

export function signedCompactCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value > 0) return `+${formatMagnitude(value)}`;
  if (value < 0) return `-${formatMagnitude(Math.abs(value))}`;
  return formatMagnitude(0);
}

function formatMagnitude(value: number): string {
  for (const unit of UNITS) {
    if (value >= unit.limit) {
      const scaled = value / unit.limit;
      const digits = scaled >= 100 ? 0 : 1;
      return `$${scaled.toFixed(digits)}${unit.suffix}`;
    }
  }
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

export function compactShares(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  for (const unit of UNITS) {
    if (Math.abs(value) >= unit.limit) {
      return `${(value / unit.limit).toFixed(1)}${unit.suffix}`;
    }
  }
  return Math.round(value).toLocaleString("en-US");
}

export function signedPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function direction(value: number | null | undefined): "up" | "down" | "flat" {
  if (value === null || value === undefined || value === 0) return "flat";
  return value > 0 ? "up" : "down";
}

export function trendGlyph(value: number | null | undefined): string {
  const trend = direction(value);
  if (trend === "up") return "▲";
  if (trend === "down") return "▼";
  return "■";
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function relativeTime(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "never";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "unknown";
  const seconds = Math.max(0, Math.round((now.getTime() - parsed.getTime()) / 1000));
  if (seconds < 60) return `${seconds} s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function relativeDays(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "no filings yet";
  const day = iso.slice(0, 10);
  const filed = Date.parse(`${day}T00:00:00Z`);
  if (Number.isNaN(filed)) return "unknown";
  const todayUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const days = Math.max(0, Math.round((todayUtc - filed) / 86_400_000));
  if (days === 0) return "today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

export function emphasisClass(netValue: number): string {
  if (netValue === 0) return "border-line";
  const strong = Math.abs(netValue) >= 10_000_000;
  const moderate = Math.abs(netValue) >= 1_000_000;
  if (strong) return netValue > 0 ? "border-buy/70" : "border-sell/70";
  if (moderate) return netValue > 0 ? "border-buy/40" : "border-sell/40";
  return "border-line";
}
