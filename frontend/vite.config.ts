import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const apiTarget = process.env.VITE_API_PROXY ?? "http://127.0.0.1:8000";

// The same paths `ops/nginx.conf` proxies, so `vite preview` serves the built
// bundle in the deployed shape for the production smoke test.
const proxy = {
  "/api": {
    target: apiTarget,
    changeOrigin: true,
  },
  "/healthz": apiTarget,
  "/readyz": apiTarget,
  "/metrics": apiTarget,
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy,
  },
  preview: {
    port: 5184,
    strictPort: true,
    proxy,
  },
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
