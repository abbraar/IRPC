import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

/** Match uvicorn `--port` (default 8000). On some Windows setups port 8000 is reserved — use 8080. */
function buildApiProxy(apiOrigin) {
  const paths = [
    "/excavations",
    "/infrastructure",
    "/projects",
    "/incidents",
    "/analyze",
    "/analyze-location",
    "/dashboard-summary",
    "/generate-data",
    "/health",
  ];
  return Object.fromEntries(paths.map((p) => [p, apiOrigin]));
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiPort = env.VITE_BACKEND_PORT || "8000";
  const devOrigin = env.VITE_DEV_API_ORIGIN?.trim();
  const apiOrigin = devOrigin || `http://127.0.0.1:${apiPort}`;

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: buildApiProxy(apiOrigin),
    },
    preview: {
      port: 4173,
      proxy: buildApiProxy(apiOrigin),
    },
  };
});
