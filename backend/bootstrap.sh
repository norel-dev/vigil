#!/bin/sh
# Register the datastores the compose file provides, once the API is up.
#
# A datastore is not configuration: it is registered through the API by a
# platform administrator, which is what lets several of them exist at once.
# So the compose file cannot simply declare one, and this script stands in for
# the administrator who would otherwise POST them by hand.
#
# It is idempotent. Each store is looked up first and only created if it is
# missing, so `docker compose up -d` on an existing volume changes nothing.
# Nothing here is a migration: delete a datastore through the API and it comes
# back the next time this runs.

set -eu

API="${API_URL:-http://api:8000}"
CONFIG="${CONFIG_FILE:-/config.docker.yaml}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-minio:9000}"
MINIO_USER="${MINIO_ROOT_USER:-dataplatform}"
MINIO_PASSWORD="${MINIO_ROOT_PASSWORD:-dataplatform-secret}"

# The administrator's key is read out of the same file the API was configured
# from, rather than repeated here, so that changing it in one place is enough.
KEY="$(sed -n 's/^[[:space:]]*api_key:[[:space:]]*"\(.*\)".*/\1/p' "$CONFIG" | head -n 1)"
if [ -z "$KEY" ]; then
    echo "seed: no api_key found in $CONFIG" >&2
    exit 1
fi

# depends_on already waits for the API's healthcheck; this is here so that a
# `docker compose run seed` against a starting API waits rather than failing.
attempt=0
until curl -fsS -o /dev/null "$API/"; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        echo "seed: $API never answered" >&2
        exit 1
    fi
    sleep 2
done

# Register the datastore named $1 with the body $2, unless it is already there.
register() {
    name="$1"
    body="$2"

    existing="$(curl -sS -o /dev/null -w '%{http_code}' \
        -H "Authorization: Bearer $KEY" "$API/datastores/$name")"
    if [ "$existing" = "200" ]; then
        echo "seed: $name is already registered"
        return 0
    fi

    status="$(curl -sS -o /tmp/seed-response -w '%{http_code}' \
        -X POST "$API/datastores/" \
        -H "Authorization: Bearer $KEY" \
        -H 'Content-Type: application/json' \
        -d "$body")"
    if [ "$status" != "201" ]; then
        echo "seed: registering $name failed with HTTP $status" >&2
        cat /tmp/seed-response >&2
        echo >&2
        exit 1
    fi
    echo "seed: registered $name"
}

# Two SQLite stores rather than one, because a single datastore cannot show
# what datastores are for: a table lands in the store its project named, and
# proving that takes somewhere else it could have gone. Each is a file in the
# API container's /data/sqlite volume, with a file per project beside it.
register 'sqlite-main' '{
  "name": "sqlite-main",
  "description": "SQLite tables, on the API container. The default place to put a table.",
  "visibility": "public",
  "datastore": {
    "implementation": "sqlite",
    "sqlite_connection_string": "/data/sqlite/main.db"
  }
}'

register 'sqlite-scratch' '{
  "name": "sqlite-scratch",
  "description": "A second SQLite store, for throwaway tables.",
  "visibility": "public",
  "datastore": {
    "implementation": "sqlite",
    "sqlite_connection_string": "/data/sqlite/scratch.db"
  }
}'

# Blobs. `secure` is false because the compose network speaks plain HTTP, and
# the expiry is short for the same reason it is short anywhere: a signed URL
# is the whole of the permission once it has left the platform.
register 'minio-blobs' "{
  \"name\": \"minio-blobs\",
  \"description\": \"MinIO object storage, for blobs. Console on http://localhost:9001.\",
  \"visibility\": \"public\",
  \"datastore\": {
    \"implementation\": \"minio\",
    \"endpoint\": \"$MINIO_ENDPOINT\",
    \"access_key\": \"$MINIO_USER\",
    \"secret_key\": \"$MINIO_PASSWORD\",
    \"secure\": false,
    \"presigned_url_expiry_seconds\": 900
  }
}"

echo "seed: done. The platform's storage is registered; GET /datastores/ lists it."
