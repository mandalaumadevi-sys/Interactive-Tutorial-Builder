import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The UI talks to the backend over absolute URLs (see src/api.js), so no dev proxy is needed.
// `base: './'` keeps the production build relocatable (served from any static path, e.g. dist/).
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: { host: "127.0.0.1", port: 5173, strictPort: true },
  preview: { host: "127.0.0.1", port: 5173, strictPort: true },
});
