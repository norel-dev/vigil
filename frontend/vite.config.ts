import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Two proxies, both of which exist because the browser is a third party the
 * platform was not built for.
 *
 * `/api` reaches the API. The API sets no CORS headers — it expects to be
 * called by something holding a key, not by a page — so the console talks to
 * it same-origin and lets the dev server cross the boundary.
 *
 * `/blob` reaches MinIO. The API signs upload and download URLs against the
 * hostname it knows the object store by, which is `minio:9000` on the compose
 * network and unreachable from a laptop. The signature covers the Host header,
 * so the URL cannot simply be rewritten to localhost: it has to be sent to
 * localhost while still claiming to be addressed to `minio:9000`. That is the
 * one thing this proxy does.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/blob": {
        target: "http://127.0.0.1:9000",
        changeOrigin: false,
        // Set on the options rather than in a `proxyReq` handler. A request
        // carrying `Expect: 100-continue` has already flushed its headers by
        // the time that event fires, so a Host written there would be dropped
        // and the store would answer SignatureDoesNotMatch — on large uploads
        // only, which is the worst possible way for this to fail.
        headers: { Host: "minio:9000" },
        rewrite: (path) => path.replace(/^\/blob/, ""),
      },
    },
  },
});
