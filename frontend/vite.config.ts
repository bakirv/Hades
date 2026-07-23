import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite config. The API base URL is injected via VITE_API_BASE_URL (see .env).
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
  },
  preview: {
    host: true,
    port: 5173,
  },
});
