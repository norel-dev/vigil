# The console, built and served on Bun.
#
# The first stage type-checks and bundles the source; the second carries only
# the bundle and server/, which needs nothing but Bun itself, on a distroless
# base with no shell, no package manager and no root.
#
#   docker build -t vigil-frontend frontend/
#   docker run -p 8080:8080 \
#     -e API_PROXY_TARGET=http://backend:8000 \
#     -e BLOB_PROXY_TARGET=http://minio:9000 \
#     vigil-frontend
#
# BLOB_SIGNED_HOST must be the host the API signs object URLs for (minio:9000
# by default); see server/routes.ts.

FROM oven/bun:1.4.2-slim AS build

WORKDIR /app

# Dependencies first, so that changing the source does not reinstall them.
# There is no bun.lock; bun reads the versions out of package-lock.json, and
# --frozen-lockfile fails the build rather than resolve anything newer.
COPY package.json package-lock.json ./
RUN bun install --frozen-lockfile

COPY . .
RUN bun --bun run build


FROM oven/bun:1.4.2-distroless

WORKDIR /app

COPY --from=build /app/dist ./dist
COPY server ./server

ENV NODE_ENV=production \
    PORT=8080 \
    STATIC_ROOT=/app/dist

# distroless's nonroot user. The files above stay root's, so the process
# cannot rewrite what it serves.
USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["bun", "-e", "const r = await fetch('http://127.0.0.1:8080/'); process.exit(r.ok ? 0 : 1)"]

# The base's entrypoint is bun.
CMD ["server/serve.ts"]
