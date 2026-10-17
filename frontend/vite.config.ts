import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import { proxyRoutes } from "./server/routes";

/** The dev server's half of `server/routes.ts`; `server/serve.ts` is the other. */
function asViteProxy({ prefix, target, host }: ReturnType<typeof proxyRoutes>[number]): ProxyOptions {
  return {
    target,
    // A route that names its own Host keeps it; one that does not gets the
    // target's, which is what `changeOrigin` means.
    changeOrigin: host === undefined,
    // Set on the options rather than in a `proxyReq` handler. A request
    // carrying `Expect: 100-continue` has already flushed its headers by the
    // time that event fires, so a Host written there would be dropped and the
    // store would answer SignatureDoesNotMatch — on large uploads only, which
    // is the worst possible way for this to fail.
    headers: host === undefined ? undefined : { Host: host },
    rewrite: (path) => path.slice(prefix.length),
  };
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(proxyRoutes().map((route) => [route.prefix, asViteProxy(route)])),
  },
});
