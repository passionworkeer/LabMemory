import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5174,
    proxy: {
      "/api": "http://localhost:8081",
      "/web": "http://localhost:8081",
      "/v1": "http://localhost:8081",
      "/health": "http://localhost:8081",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
