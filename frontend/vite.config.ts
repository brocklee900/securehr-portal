import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

declare const process: { env: Record<string, string | undefined> };   // Node global (no @types/node needed)

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, port: 5173, hmr: { clientPort: 443, protocol: "wss" },
    allowedHosts: [`portal.${process.env.SECUREHR_DOMAIN || "localhost"}`],   // set by docker-compose.yml
  },
});
