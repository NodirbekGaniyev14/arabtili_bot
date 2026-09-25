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
      "/api": "http://localhost:8000",
      // K25 Oktagon — jonli jang WebSocket orqali
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
