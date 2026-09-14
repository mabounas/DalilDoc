import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // Le back-office est servi sous /admin/ (même domaine que la borne, API en relatif).
  base: "/admin/",
  server: {
    port: 3001,
    proxy: { "/api": process.env.API_INTERNAL_URL || "http://localhost:8000" },
  },
  preview: { port: 3001 },
});
