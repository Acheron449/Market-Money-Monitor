import { formatDateTime } from "../lib/format";

interface FooterProps {
  lookbackMonths: number;
  generatedAt: string;
}

export function Footer({ lookbackMonths, generatedAt }: FooterProps) {
  return (
    <footer className="mt-8 border-t border-line pt-4 text-xs leading-relaxed text-muted">
      <p>
        Form 4 filings can lag by up to two business days and 13F holdings are reported quarterly.
        Signals use a {lookbackMonths}-month lookback over open-market purchases and sales only.
        Data refreshed {formatDateTime(generatedAt)}.
      </p>
      <p className="mt-1 font-medium text-fg/80" data-testid="disclaimer">
        For information only — not investment advice.
      </p>
    </footer>
  );
}
