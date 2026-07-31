import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// During development the dev server proxies API calls to the local FastAPI
// backend. In a normal run FastAPI serves this build directly and the proxy
// is not used.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
