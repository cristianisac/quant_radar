import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Proxy /api/* to the FastAPI server (Phase 14a) running on :8000 in
// the dev container. Avoids CORS during dev and matches how the
// production build will be served (FastAPI mounts the built bundle in
// Phase 14d).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
