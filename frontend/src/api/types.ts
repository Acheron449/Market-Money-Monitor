export type Action = "buy" | "sell" | "other";

export interface Signal {
  ticker: string;
  netValue: number;
  txnCount: number;
  starredCount: number;
  clusterBuy: boolean;
}

export interface Quote {
  price: number;
  changePct: number;
  asOf: string;
  source: string;
  delayed: boolean;
}

export interface Txn {
  key: string;
  ticker: string;
  date: string;
  name: string;
  role: string | null;
  action: Action;
  typeLabel: string;
  shares: number;
  value: number | null;
  starred: boolean;
  is10b5_1?: boolean;
}

export interface Freshness {
  asOf: string | null;
  stale: boolean;
}

export interface Dashboard {
  signals: Signal[];
  quotes: Record<string, Quote>;
  tape: Txn[];
  lookbackMonths: number;
  latestFilingDate: string | null;
  generatedAt: string;
  freshness: Record<string, Freshness>;
}

export interface HistoryPoint {
  date: string;
  close: number;
}

export interface Holder {
  rank: number;
  institution: string;
  shares: number;
  value: number;
  qoqChangePct: number | null;
  reportPeriod: string;
}

export interface RefreshResponse {
  jobId: string;
  status: string;
}

export interface Watchlist {
  tickers: string[];
}

export interface CrossCheckSummary {
  at: string | null;
  provider: string | null;
  checked: number;
  discrepancies: number;
  status: string;
}

export interface BulkLoadSummary {
  at: string | null;
  rows: number;
  status: string;
}

export interface Discrepancy {
  id: number;
  checkedAt: string;
  symbol: string;
  accessionNo: string;
  lineNo: number;
  field: "shares" | "value";
  primaryValue: number | null;
  secondaryValue: number | null;
  differencePct: number;
  provider: string;
}

export interface DataQuality {
  crossCheck: CrossCheckSummary;
  bulkInsider: BulkLoadSummary;
  bulk13f: BulkLoadSummary;
  discrepancies: Discrepancy[];
}

export interface Alert {
  id: number;
  kind: string;
  symbol: string;
  title: string;
  body: string;
  createdAt: string;
  channels: string[];
  status: string;
}
