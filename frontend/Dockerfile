FROM oven/bun:1.4.2-slim AS build

WORKDIR /app

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

USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["bun", "-e", "const r = await fetch('http://127.0.0.1:8080/'); process.exit(r.ok ? 0 : 1)"]

CMD ["server/serve.ts"]
