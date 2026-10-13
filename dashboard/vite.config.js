import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: `npm run dev` proxies /api to the Python API (python -m api.server --port 8000).
// Prod: set VITE_API_BASE to the deployed API URL at build time.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
});
