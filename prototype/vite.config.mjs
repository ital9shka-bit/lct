import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  build: {
    outDir: "dist/client",
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    host: "0.0.0.0",
    allowedHosts: ["terminal.local"],
    warmup: {
      clientFiles: ["./src/main.jsx"],
    },
    proxy: {
      "/auth": "http://127.0.0.1:8000",
      "/objects": "http://127.0.0.1:8000",
      "/mail": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
  plugins: [react()],
});
