import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Dev mirror of the nginx /api/ proxy: same-origin calls work locally.
    // /api/health is the backend liveness probe (backend serves /health).
    proxy: {
      "^/api/health$": { target: "http://localhost:8000", rewrite: () => "/health" },
      "/api": "http://localhost:8000",
    },
  },
});
