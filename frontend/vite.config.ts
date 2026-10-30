import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Development: the API runs in Docker (compose.override.yaml publishes it on 8010).
const api = "http://localhost:8010";
const proxied = ["/auth", "/app", "/admin", "/api", "/health", "/docs", "/openapi.json", "/ui"];

export default defineConfig({
  plugins: [react()],
  server: { proxy: Object.fromEntries(proxied.map((path) => [path, api])) },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
