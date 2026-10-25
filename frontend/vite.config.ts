import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// In development the API runs on :8102; the browser calls /api/... on the same origin and Vite forwards it,
// so there is no CORS setup. In production nginx (docker-compose) or Render does the same forwarding.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5182,
    proxy: { "/api": { target: "http://127.0.0.1:8102", rewrite: (p) => p.replace(/^\/api/, "") } },
  },
  preview: {
    port: 5182,
    proxy: { "/api": { target: "http://127.0.0.1:8102", rewrite: (p) => p.replace(/^\/api/, "") } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
