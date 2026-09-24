import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    // cloudflared/ngrok tunnel domenlari uchun
    allowedHosts: true,
    proxy: {
      "/api": "http://localhost:8000",
      // K25 Oktagon — jonli jang WebSocket orqali
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
