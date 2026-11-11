import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev: http://127.0.0.1:5173 com proxy para o backend; produção: o backend serve o dist/
export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", proxy: { "/api": "http://127.0.0.1:8765" } },
});
