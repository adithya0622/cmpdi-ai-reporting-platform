import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/auth": "http://localhost:8000",
      "/documents": "http://localhost:8000",
      "/reports": "http://localhost:8000",
      "/analytics": "http://localhost:8000",
      "/query": "http://localhost:8000",
      "/extractions": "http://localhost:8000",
      "/admin": "http://localhost:8000",
    },
  },
});
