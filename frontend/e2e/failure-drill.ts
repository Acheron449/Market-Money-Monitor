import { execFileSync } from "node:child_process";
import path from "node:path";

export const BACKEND = path.join(process.cwd(), "..", "backend");

/** Run the AC-03/AC-04 drill against the seeded E2E database. */
export function runFailureDrill(mode: "fallback" | "outage"): string {
  return execFileSync("uv", ["run", "python", "scripts/e2e_failure_drill.py", "--mode", mode], {
    cwd: BACKEND,
    env: { ...process.env, DATABASE_URL: "sqlite+aiosqlite:///./e2e.db" },
    timeout: 30_000,
    encoding: "utf8",
    stdio: "pipe",
  });
}

/** Put the aged quote rows back in the freshness window after an outage scan. */
export function restoreQuoteFreshness(): void {
  const script = [
    "import datetime, sqlite3",
    "connection = sqlite3.connect('e2e.db', timeout=10)",
    "connection.execute(",
    "    'UPDATE quote SET as_of = ?',",
    "    (datetime.datetime.now(datetime.UTC).replace(tzinfo=None).isoformat(sep=' '),),",
    ")",
    "connection.commit()",
    "connection.close()",
  ].join("\n");
  execFileSync("uv", ["run", "python", "-c", script], {
    cwd: BACKEND,
    timeout: 30_000,
    stdio: "pipe",
  });
}
