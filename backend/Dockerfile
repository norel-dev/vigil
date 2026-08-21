# The API, as the compose file runs it.
#
# The image carries the dependencies and the source; the compose file mounts
# the source over it read-only so that editing a file on the host reloads the
# server. Nothing is written into /app at runtime, which is what lets that
# mount be read-only: the virtual environment lives outside the project and
# bytecode is not written at all.

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, so that changing the source does not reinstall them.
# The project itself declares no build system, so it is never installed: it is
# imported from the working directory, exactly as it is outside Docker.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .

# Created here rather than by the compose file so that the named volume
# mounted over /data inherits them. The metadata database lives in the first;
# the SQLite datastores the platform is handed live in the second.
RUN mkdir -p /data/metadata /data/stores

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=40s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/', timeout=2)"]

CMD ["fastapi", "dev", "main.py", "--host", "0.0.0.0", "--port", "8000"]
