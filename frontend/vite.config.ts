import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({ plugins: [react()], server: { proxy: {
  "/api/knowledge": { target: "http://localhost:8001", rewrite: (path) => path.replace(/^\/api\/knowledge/, "") },
  "/api/inbox": { target: "http://localhost:8002", rewrite: (path) => path.replace(/^\/api\/inbox/, "") },
  "/api/scopes": { target: "http://localhost:8003", rewrite: (path) => path.replace(/^\/api/, "") },
} } });
