/**
 * Where the console's two same-origin prefixes lead, for whichever server is
 * in front of it: Vite's in development, `serve.ts` in the image.
 *
 * `/api` reaches the API. The API sets no CORS headers — it expects to be
 * called by something holding a key, not by a page — so the console talks to
 * it same-origin and lets the server in front cross the boundary.
 *
 * `/blob` reaches the object store. The API signs upload and download URLs
 * against the hostname it knows the store by, which is `minio:9000` on the
 * compose network and unreachable from a browser. The signature covers the
 * Host header, so the request has to go to wherever the store is reachable
 * while still claiming to be addressed to the host it was signed for.
 *
 * Both targets default to the laptop; inside a container 127.0.0.1 is the
 * container, so there they have to be set.
 */
export interface ProxyRoute {
  /** The path prefix the console uses; stripped before forwarding. */
  prefix: string;
  /** Origin of the upstream, e.g. `http://backend:8000`. */
  target: string;
  /** Host header to send. Unset means the target's own host. */
  host?: string;
}

export function proxyRoutes(env: Record<string, string | undefined> = process.env): ProxyRoute[] {
  return [
    { prefix: "/api", target: env.API_PROXY_TARGET ?? "http://127.0.0.1:8000" },
    {
      prefix: "/blob",
      target: env.BLOB_PROXY_TARGET ?? "http://127.0.0.1:9000",
      host: env.BLOB_SIGNED_HOST ?? "minio:9000",
    },
  ];
}
