import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import pkg from "./package.json";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Profil pastidagi «Arabiy · v1.x» (K26)
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  server: {
    host: true,
    // cloudflared/ngrok tunnel domenlari uchun
    allowedHosts: true,
    proxy: {
      // K30: /api/v2/live/ws — jonli ovozli suhbat ham WebSocket
      "/api": { target: "http://localhost:8000", ws: true },
      // K25 Oktagon — jonli jang WebSocket orqali
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
