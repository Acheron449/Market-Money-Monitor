import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /deploy\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5184",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "bash ../scripts/deploy_backend.sh",
      url: "http://127.0.0.1:8020/healthz",
      reuseExistingServer: false,
      timeout: 180_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      // Production build first, then serve it the way the nginx image does.
      command:
        "npx --yes pnpm@9 build && npx --yes pnpm@9 exec vite preview --host 127.0.0.1 --port 5184 --strictPort",
      url: "http://127.0.0.1:5184",
      reuseExistingServer: false,
      timeout: 180_000,
      env: { VITE_API_PROXY: "http://127.0.0.1:8020" },
    },
  ],
});
