import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // The production-shape smoke test has its own servers and config.
  testIgnore: /deploy\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 10_000,
  },
  webServer: [
    {
      command: "bash ../scripts/e2e_backend.sh",
      url: "http://127.0.0.1:8010/healthz",
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "npx --yes pnpm@9 exec vite --host 127.0.0.1 --port 5174 --strictPort",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      timeout: 120_000,
      env: { VITE_API_PROXY: "http://127.0.0.1:8010" },
    },
  ],
});
