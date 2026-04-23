import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig(({ mode }) => {
  // Merge .env* into process.env so API_PROXY_TARGET can live in frontend/.env.local
  loadEnv(mode, process.cwd(), "");
  const proxyTarget =
    process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    resolve: {
      alias: {
        // Allows "@/components/..." instead of "../../components/..."
        "@": resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
