/**
 * The console in production: the built bundle, and the two proxies the
 * browser cannot do without (see `routes.ts`), on Bun with no dependencies.
 *
 * Configured by environment:
 *   PORT               where to listen (8080)
 *   STATIC_ROOT        the built bundle (./dist)
 *   API_PROXY_TARGET, BLOB_PROXY_TARGET, BLOB_SIGNED_HOST   see routes.ts
 */
import { resolve, sep, extname } from "node:path";
import { proxyRoutes, type ProxyRoute } from "./routes";

const port = Number(process.env.PORT ?? 8080);
const root = resolve(process.env.STATIC_ROOT ?? "dist");
const routes = proxyRoutes();

/** Headers that describe one hop and must not be passed on to the next. */
const HOP_BY_HOP = [
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
];

// ---------------------------------------------------------------- proxying

function routeFor(pathname: string): ProxyRoute | undefined {
  return routes.find(({ prefix }) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

/**
 * Forward one request, keeping its path and query byte for byte — the query of
 * a signed URL is the signature, and a re-encoded `+` or `%2F` invalidates it.
 * Bodies stream through in both directions, so an upload of any size never
 * sits in memory.
 */
async function forward(request: Request, route: ProxyRoute, client: string): Promise<Response> {
  const incoming = new URL(request.url);
  const target = new URL(route.target);
  const upstream = `${target.origin}${incoming.pathname.slice(route.prefix.length) || "/"}${incoming.search}`;

  const headers = new Headers(request.headers);
  for (const name of HOP_BY_HOP) headers.delete(name);
  headers.set("host", route.host ?? target.host);
  headers.set("x-forwarded-host", incoming.host);
  headers.set("x-forwarded-proto", incoming.protocol.slice(0, -1));
  headers.set("x-forwarded-for", client);

  let response: Response;
  try {
    response = await fetch(upstream, {
      method: request.method,
      headers,
      body: request.body,
      redirect: "manual",
      // Pass the upstream's encoding through untouched rather than inflating
      // it here and sending a body that no longer matches its headers.
      decompress: false,
      signal: request.signal,
    });
  } catch (error) {
    if (request.signal.aborted) return new Response(null, { status: 499 });
    console.error(`upstream ${route.prefix} unreachable at ${target.origin}:`, error);
    return new Response(`${route.prefix} is unreachable`, { status: 502 });
  }

  const outgoing = new Headers(response.headers);
  for (const name of HOP_BY_HOP) outgoing.delete(name);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: outgoing,
  });
}

// ---------------------------------------------------------------- static files

const SECURITY_HEADERS = {
  "x-content-type-options": "nosniff",
  // SAMEORIGIN, not DENY: the pdf viewer frames `/blob` from this origin.
  "x-frame-options": "SAMEORIGIN",
  "referrer-policy": "strict-origin-when-cross-origin",
};

/** File names under assets/ carry a content hash, so they never change. */
const IMMUTABLE = "public, max-age=31536000, immutable";
/** Everything else — index.html above all — is checked on every load. */
const REVALIDATE = "no-cache";

const COMPRESSIBLE = new Set([".html", ".js", ".css", ".svg", ".json", ".txt", ".map"]);

/** The bundle never changes inside the image, so each file is compressed once. */
const gzipped = new Map<string, Uint8Array>();

async function gzipOf(path: string): Promise<Uint8Array> {
  let body = gzipped.get(path);
  if (!body) {
    body = Bun.gzipSync(await Bun.file(path).bytes());
    gzipped.set(path, body);
  }
  return body;
}

/** The file a path names, or undefined if it names nothing inside the root. */
async function fileAt(pathname: string): Promise<string | undefined> {
  let decoded: string;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return undefined;
  }
  const path = resolve(root, `.${decoded}`);
  if (!path.startsWith(root + sep)) return undefined;
  const file = Bun.file(path);
  // A directory "exists" too, and has no size worth serving.
  return (await file.exists()) && file.size > 0 ? path : undefined;
}

async function serveStatic(request: Request): Promise<Response> {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response(null, { status: 405, headers: { allow: "GET, HEAD", ...SECURITY_HEADERS } });
  }

  const { pathname } = new URL(request.url);
  let path = await fileAt(pathname);
  if (!path) {
    // A missing hashed asset is a stale page asking for last deploy's bundle;
    // answering it with index.html would only fail later and more confusingly.
    if (pathname.startsWith("/assets/")) {
      return new Response("not found", { status: 404, headers: SECURITY_HEADERS });
    }
    path = resolve(root, "index.html");
  }

  const headers: Record<string, string> = {
    ...SECURITY_HEADERS,
    "cache-control": pathname.startsWith("/assets/") ? IMMUTABLE : REVALIDATE,
    "content-type": Bun.file(path).type,
  };

  const extension = extname(path);
  if (COMPRESSIBLE.has(extension)) {
    headers.vary = "accept-encoding";
    if (/\bgzip\b/.test(request.headers.get("accept-encoding") ?? "")) {
      headers["content-encoding"] = "gzip";
      return new Response(await gzipOf(path), { headers });
    }
  }
  // Bun drops the body of a HEAD response itself, keeping its length.
  return new Response(Bun.file(path), { headers });
}

// ---------------------------------------------------------------- server

const server = Bun.serve({
  port,
  hostname: "0.0.0.0",
  // Uploads stream through to the store, which sets its own limits.
  maxRequestBodySize: Number.MAX_SAFE_INTEGER,
  // Seconds a connection may sit silent; a slow query on the API is the
  // longest legitimate silence. 255 is Bun's ceiling.
  idleTimeout: 255,
  async fetch(request, server) {
    const started = performance.now();
    const { pathname } = new URL(request.url);
    const route = routeFor(pathname);
    const response = route
      ? await forward(request, route, server.requestIP(request)?.address ?? "")
      : await serveStatic(request);
    // The path only: the query of a `/blob` request is a live credential.
    console.log(
      `${request.method} ${pathname} ${response.status} ${(performance.now() - started).toFixed(0)}ms`,
    );
    return response;
  },
  error(error) {
    console.error(error);
    return new Response("internal error", { status: 500 });
  },
});

console.log(`serving ${root} on :${server.port}`);
for (const { prefix, target, host } of routes) {
  console.log(`  ${prefix} -> ${target}${host ? ` (Host: ${host})` : ""}`);
}

// As PID 1 nothing exits on a signal unless told to. Stop taking new
// connections, let the ones in flight finish, then go.
for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.on(signal, async () => {
    await server.stop();
    process.exit(0);
  });
}
