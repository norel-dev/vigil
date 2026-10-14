# The console, as the compose file runs it: Vite's dev server, on Bun.
#
# The image carries the dependencies and the source; the compose file mounts
# the source over it read-only so that editing a file on the host hot-reloads
# the page. The dependencies live one directory above the project, in
# /srv/node_modules, so that mount does not hide them: module resolution walks
# up from /srv/app and finds them there. Vite's own cache goes in that same
# directory, which is what lets the source mount be read-only.
#
# There is no Node in this image, so Vite runs on Bun's runtime. The one place
# that matters is the /blob proxy and its Host header: if large uploads through
# the console fail with SignatureDoesNotMatch, this is the first suspect.

FROM oven/bun:1.4.2-slim

WORKDIR /srv

# Dependencies first, so that changing the source does not reinstall them.
# There is no bun.lock yet; bun install reads the versions out of
# package-lock.json instead, so the image gets what npm would have installed.
COPY package.json package-lock.json ./
RUN bun install

WORKDIR /srv/app
COPY . .

ENV PATH=/srv/node_modules/.bin:$PATH \
    VITE_CACHE_DIR=/srv/node_modules/.vite

EXPOSE 5173

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD ["bun", "-e", "const r = await fetch('http://localhost:5173/'); process.exit(r.ok ? 0 : 1)"]

CMD ["vite", "--host", "0.0.0.0", "--port", "5173"]
