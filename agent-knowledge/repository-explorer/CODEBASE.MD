# Vigil — data platform monorepo (`backend/` FastAPI API + `frontend/` React console)

> **This file is the canonical report.** It lives at `agent-knowledge/repository-explorer/CODEBASE.MD`
> at the repository root (here explored from the worktree
> `/Users/norel/code/vigil/worktrees/claude2`; main checkout `/Users/norel/code/vigil`).
> Two older reports are **stale** and describe a previous layout
> (`/Users/norel/dataplatform/app/...` at `7e30d98`):
> `backend/agent-knowledge/repository-explorer/CODEBASE.MD` and
> `frontend/agent-knowledge/repository-explorer/CODEBASE.MD`. Ignore them.

## Commit

- HEAD: **`6bfcab9`** — "add gitignore" (branch `claude2`, a worktree; main branch is `main`).
  Working tree clean at time of writing.
- Recent history (newest first):
  - `6bfcab9` — root `.gitignore` containing only `worktrees/`.
  - `8b96be0` — "refactor: move local deployment stack to outermost folder": root
    `docker-compose.yaml` + root `README.md`, `backend/bootstrap.sh` (replaces
    `backend/scripts/seed-datastores.sh`), PostgreSQL-only metadata DB (psycopg),
    `ObjectInUseError` → 409, backend README "Running it" rewritten for the root compose.
  - `018e21f` — "Build the console into a distroless Bun image that serves the bundle and proxies
    /api and /blob, replacing the Vite dev-server image": new `frontend/server/{routes,serve}.ts`,
    two-stage `frontend/Dockerfile`, `vite.config.ts` now reads routes from `server/routes.ts`,
    compose gains a `frontend` service on port 8080.
  - `65c022b` — frontend Dockerfile (first version, Vite dev server; now superseded).
  - `532c63a` — MinIO image switched to `cgr.dev/chainguard/minio`.
  - earlier: `9cca81a`, `7e30d98`, `eff821a` (primary keys in console), `f3833a6` (backend primary
    keys), `ee639a5` (members page), ...
- To refresh: `git log 6bfcab9..HEAD`.

## Description

Vigil ("a simple and modular data platform designed to abstractly accommodate any query engine
and blob store") is two applications in one git repo (~149 tracked-ish files outside
`.venv`/`node_modules`):

1. **`backend/` — the API.** Python **3.14** + FastAPI (pyproject name `api`). Abstracts
   management of data held across several underlying stores (SQLite for tables, MinIO/S3 for
   blobs). Authentication by **API keys the platform issues itself** (`dpk_…`, stored only as a
   SHA-256 digest). Authorization delegated wholesale to an **Open Policy Agent** Rego policy;
   fails **closed** (503) if OPA is unreachable. Metadata DB is **PostgreSQL only**
   (`postgresql+psycopg://`), schema owned by **Alembic** revisions applied automatically at
   startup. ~52 Python modules under `src/` + `main.py`; 17 `test_*.py` + `conftest.py`;
   6 migrations + `env.py`; 2 Rego files.
2. **`frontend/` — the console.** React 19 + TypeScript + Vite SPA (`"name":
   "dataplatform-console"`). Keyboard-first, vim/Neovim-flavoured UI: blobs (upload + view
   image/video/audio/pdf/html/markdown/text), tables (create with primary key, add columns,
   insert rows, run SQL), workspaces (= projects) with membership on its own page. 34 source
   files under `src/` (7 `lib`, 12 components, 10 viewers, `App.tsx`, `main.tsx`, 3 CSS) plus a
   tiny **Bun production server** in `server/` (`routes.ts`, `serve.ts`). Runtime deps: only
   `react`, `react-dom`.

Core ideas (shared vocabulary):

- **Two scopes.** `system` — **datastores** and **users**; platform administrators only.
  `project` — **projects** and their **tables** and **blobs**; governed by `ProjectRole`
  (`viewer < editor < admin < owner`).
- **The API never decides permissions itself.** It builds `AuthorizationRequest`s (with a
  computed `scope`) and asks OPA. Listings filter via one `allowed_resource_ids` call.
- **Membership is two powers.** `project.manage_members` (admin+) vs `project.remove_members`
  (owner). Only an owner may grant `owner`; `owner` can never be taken back from inside the
  project. Platform admins stand outside it.
- **Limits enforced by the engine, not by parsing.** SQL privilege chosen from the policy then
  enforced by SQLite's authorizer callback; blob permission is the presigned-URL signature.
- **The platform never carries blob bytes** — create returns a record + presigned `PUT` URL.
- **Console ideas:** no form changes a table without printing its SQL first; one place decides
  how to view bytes (`viewers/registry.ts`); `lib/authz.ts` mirrors the policy only to avoid
  offering refused acts; a workspace's contents and its access are two pages; one place decides
  where `/api` and `/blob` lead (`server/routes.ts`), read by both Vite and `serve.ts`.

Entrypoints: whole stack `docker compose up -d` **from the repo root** → console at
`http://localhost:8080`, API at `:8000`; backend alone `uv run fastapi dev main.py` (in
`backend/`, needs `config.yaml` copied from `config.example.yaml`); frontend dev `npm run dev`
→ `http://localhost:5173`.

## File Structure

| Path | Description | Usage frequency |
|---|---|---|
| `/` (repo root) | `README.md` (Vigil intro; console at :8080, key `BOOTSTRAP_API_KEY`), `docker-compose.yaml`, `.gitignore` (`worktrees/` only), `backend/`, `frontend/`, `agent-knowledge/` (this report), `worktrees/` (git worktrees, ignored). | rare |
| `docker-compose.yaml` | **Dev stack.** `x-config` anchors (Postgres creds default `postgres`/`password`/`postgres`; MinIO root `dataplatform`/`dataplatform-secret`; ports `BACKEND_PORT` 8000, `OPA_PORT` 8181, `MINIO_PORT` 9000, `MINIO_CONSOLE_PORT` 9001, `POSTGRES_PORT` 5432, **`FRONTEND_PORT` 8080**). Inline `configs.backend_config` YAML (mounted at `/app/config.yaml` in backend = the default path, and `/config.yaml` in bootstrap) with bootstrap admin `root@example.com`, key `BOOTSTRAP_API_KEY` (default `dpk_local_docker_compose_development_key`), OPA `http://opa:8181`. Services: `backend` (`vigil-backend`, build `backend/`, volume `sqlite_data:/data/sqlite`, python urllib healthcheck), **`frontend`** (`vigil-frontend`, build `frontend/`, depends on healthy backend, env `API_PROXY_TARGET=http://backend:8000`, `BLOB_PROXY_TARGET=http://minio:9000`, `BLOB_SIGNED_HOST=minio:9000`), `opa` (`openpolicyagent/opa:1.19.0`, mounts `./backend/policies:/policies:ro`, decision logs to console), `minio` (`cgr.dev/chainguard/minio`, healthcheck `mc ready local`), `postgres` (`postgres:18`), `bootstrap` (`curlimages/curl:8.11.1`, runs `backend/bootstrap.sh` once). Volumes `postgres_data`, `sqlite_data`, `minio_data`. | dev |
| `backend/` | The API project (uv-managed). | constant |
| `backend/main.py` | Entry: `main()` loads config via `src.platform.environment`, builds app, module-level `app`; exits 1 on `ConfigurationError` with a hint to copy `config.example.yaml`. | on start |
| `backend/config.example.yaml` | Template for `config.yaml`: Postgres at `localhost:5432` (root compose creds), `bootstrap_platform_admins` with `api_key: "REPLACE_ME"`, OPA `localhost:8181`. | setup |
| `backend/bootstrap.sh` | POSIX sh "administrator": reads first `api_key` out of `$CONFIG_FILE` via `sed`, waits for `$API_URL/` (30 tries), idempotently registers `sqlite-main` (`/data/sqlite/main.db`), `sqlite-scratch` (`/data/sqlite/scratch.db`), `minio-blobs` (endpoint `$MINIO_ENDPOINT`, root creds, `secure:false`, expiry 900), all `visibility: public`. Log prefix still `seed:`; defaults still name `http://api:8000` and `/config.docker.yaml` (overridden by compose env). | dev |
| `backend/Dockerfile` | `ghcr.io/astral-sh/uv:python3.14-bookworm-slim`, venv `/opt/venv`, `uv sync --frozen --no-install-project`, copies source (no bind mount — rebuild to change), `HEALTHCHECK` on `/`, `CMD fastapi dev main.py --host 0.0.0.0 --port 8000`. | dev |
| `backend/.dockerignore`, `.gitignore`, `.python-version`, `.claude/settings.json` | Ignore lists (exclude `config.yaml`); Python pin; Claude plugin settings. | setup |
| `backend/README.md` | Access model, catalogue, visibility, tables & privileges, primary keys, blobs & signed URLs, **running (root compose, current)**, keys, migrations, tests, layout. Best single doc on the backend. | reference |
| `backend/pyproject.toml`, `uv.lock` | Deps, pytest/coverage/ruff settings. | setup |
| `backend/alembic.ini` | Alembic settings; deliberately no `sqlalchemy.url` (config chosen by `DATAPLATFORM_CONFIG`). | migrations |
| `backend/migrations/` | `env.py`, `README`, `script.py.mako`, `versions/`: `0001_baseline`, `0002_system_level_datastores`, `0003_project_tables`, `0004_api_keys`, `0005_project_blobs`, `0006_datastore_visibility`. Revisions never import from `src`; PostgreSQL-only. | history |
| `backend/policies/dataplatform/` | `authz.rego`, `authz_test.rego` (`opa test policies -v`). Mounted into OPA. | every request |
| `backend/src/app.py` | `create_app` — wires OPA, mounts routers, lifespan (migrate, bootstrap admins). Only module naming OPA. | on start |
| `backend/src/features/` | One package per offering: `users/`, `projects/`, `tables/`, `blobs/`, `datastores/` — each `model.py`, `service.py`, `router.py` (+ `storage.py` where it owns a storage protocol; `datastores/catalogue.py`). | every request |
| `backend/src/features/datastores/implementations/` | `base.py`, `sqlite.py`, `minio.py`, `_sqlite_privileges.py`. | every request |
| `backend/src/identity/` | Who the caller is: `keys.py`, `model.py`, `service.py`, `caller.py`, `bootstrap.py`. | every request |
| `backend/src/authz/` | What the caller may do: `policy.py`, `opa.py`, `enforcement.py`. | every request |
| `backend/src/database/` | `engine.py`, `migrations.py`. Feature-agnostic. | on start |
| `backend/src/platform/` | Plumbing: `config.py`, `environment.py`, `exceptions.py`, `error_handlers.py`, `state.py`, `dependencies.py`. Feature-agnostic. | every request |
| `backend/tests/` | `conftest.py` + 17 test files: `test_api_keys`, `test_blob_access`, `test_blob_keys`, `test_blob_storage`, `test_bootstrap_admin`, `test_configuration`, `test_datastore_access`, `test_datastore_catalogue`, `test_datastore_persistence`, `test_datastore_visibility`, `test_enforcement`, `test_migrations`, `test_opa_client`, `test_project_access` (largest), `test_table_access`, `test_table_storage`, `test_user_administration`. | CI/dev |
| `backend/agent-knowledge/`, `frontend/agent-knowledge/` | Stale older reports. | never |
| `frontend/` | The console (npm/Vite for dev; Bun for the image). | constant |
| `frontend/server/routes.ts` | **Single source of proxy routing.** `ProxyRoute {prefix, target, host?}`; `proxyRoutes(env = process.env)` → `/api` → `API_PROXY_TARGET` (default `http://127.0.0.1:8000`), `/blob` → `BLOB_PROXY_TARGET` (default `http://127.0.0.1:9000`) with Host `BLOB_SIGNED_HOST` (default `minio:9000`). Used by `vite.config.ts` and `serve.ts`. | every request |
| `frontend/server/serve.ts` | **Production server on Bun, zero deps.** `Bun.serve` on `PORT` (8080), `0.0.0.0`, unlimited body size, `idleTimeout` 255. Proxies matching prefixes (strips prefix, keeps path+query byte-for-byte, drops hop-by-hop headers, sets `host`/`x-forwarded-*`, `decompress:false`, streams bodies; 502 if upstream unreachable, 499 on client abort). Otherwise serves `STATIC_ROOT` (`dist`): path-traversal guard, SPA fallback to `index.html` except missing `/assets/*` → 404, `/assets/` immutable cache else `no-cache`, in-memory gzip cache for text types, security headers (`nosniff`, `X-Frame-Options: SAMEORIGIN` for pdf frames, referrer policy), 405 for non-GET/HEAD. Logs path only (blob query is a credential). Graceful stop on SIGTERM/SIGINT. | prod/compose |
| `frontend/Dockerfile` | Two stages: `oven/bun:1.4.2-slim` → `bun install --frozen-lockfile`, `bun --bun run build`; runtime `oven/bun:1.4.2-distroless`, copies `dist` + `server`, `NODE_ENV=production PORT=8080 STATIC_ROOT=/app/dist`, user `65532:65532`, healthcheck via `bun -e fetch`, `CMD ["server/serve.ts"]`. | compose |
| `frontend/vite.config.ts` | React plugin, port 5173; proxies built from `proxyRoutes()` via `asViteProxy` (`changeOrigin` iff no `host`; Host set in options `headers`, not a `proxyReq` handler, because `Expect: 100-continue` uploads flush headers early → `SignatureDoesNotMatch`; prefix stripped by `rewrite`). | dev |
| `frontend/.dockerignore`, `.gitignore`, `index.html`, `tsconfig.json`, `package.json`, `package-lock.json`, `.claude/settings.json` | Vite shell; strict TS (`include: ["src", "vite.config.ts"]` — `server/serve.ts` itself is not type-checked); scripts `dev`/`build`/`preview`. | dev |
| `frontend/README.md` | Proxies, production server & env table, API assumptions, keyboard, buffers/workspaces, workspace pages, viewers, transport, blob tree, layout. Stale bit: "Running it" still says `cd ../backend && docker compose up -d`. | reference |
| `frontend/src/lib/` | `api.ts`, `authz.ts`, `sql.ts`, `media.ts`, `format.ts`, `tree.ts`, `text.ts`. | every render |
| `frontend/src/viewers/` | `viewer.ts`, `registry.ts`, `Frame.tsx`, `Transport.tsx`, `Image.tsx`, `Video.tsx`, `Audio.tsx`, `Pdf.tsx`, `Source.tsx`, `Unknown.tsx`. | every blob render |
| `frontend/src/components/` | `Shell.tsx`, `Rail.tsx`, `WorkspacePane.tsx`, `MembersPane.tsx`, `TablePane.tsx`, `BlobPane.tsx`, `ContactSheet.tsx`, `dialogs.tsx`, `Overlay.tsx`, `Palette.tsx`, `Gate.tsx`, `bits.tsx`. | every render |
| `frontend/src/vigil/` | Vigil design system vendored (`tokens.css`, `components.css`) + console layer `app.css` (`dp-` prefixed). `main.tsx` imports `app.css` **after** `components.css`. | every render |
| `frontend/public/` | `mark.svg`, `favicon.svg`. | rare |
| `backend/.venv/`, `frontend/node_modules/`, `**/__pycache__/` | Thousands of files; ignore. | never |

## Objects

### Backend — configuration (`backend/src/platform/config.py`, `environment.py`)
- `MINIMUM_BOOTSTRAP_KEY_LENGTH = 32`; `METADATA_DATABASE_DRIVER = "postgresql+psycopg"`.
- `DatabaseConfig` (`url`, `echo`; validator `_check_url_is_postgresql` via `sqlalchemy.make_url`),
  `BootstrapAdminConfig` (`email`, `name`, `api_key` ≥32), `AuthConfig`
  (`bootstrap_platform_admins`; `_check_admins_are_distinct`), `OpaConfig` (`url`,
  `decision_path`, `filter_path`, `request_timeout_seconds`), `AppConfig`.
- `environment.py`: **`CONFIG_PATH_VARIABLE = "DATAPLATFORM_CONFIG"`**,
  `DEFAULT_CONFIG_PATH = Path("config.yaml")`. Only place the env is read.

### Backend — exceptions (`backend/src/platform/exceptions.py`)
`DataPlatformError` → `ConfigurationError`, `SchemaMigrationError`, `ObjectNotFoundError`,
`DuplicateObjectError`, `ObjectInUseError`, `AuthenticationError`→`InvalidApiKeyError`,
`AuthorizationError`→`PolicyDecisionPointError`/`PermissionDeniedError`,
`StorageError`→`UnsuitableDataStoreError`/`TableProvisioningError`/`BlobProvisioningError`/
`QueryRefusedError`/`QueryFailedError`.

### Backend — authorization vocabulary (`backend/src/authz/policy.py`)
- `ResourceScope(StrEnum)` SYSTEM/PROJECT; `ResourceType(StrEnum)` PROJECT, DATASTORE, TABLE,
  BLOB, USER with `.scope`; `Action(StrEnum)` `project.read/update/delete/manage_members/remove_members`,
  `datastore.create/read/query/update/delete`, `table.create/read/query/write/delete`,
  `blob.create/read/download/upload/delete`, `user.create/read/issue_key`.
- `Subject`, `Resource` (computed `scope`), `MembershipChange` (`current_role`, `requested_role`;
  `None` = removal), `AuthorizationRequest`, `Decision`; Protocols `PolicyDecisionPoint`, `ResourceFilter`.

### Backend — persistence models
- `User` — `src/features/users/model.py`. `ApiKey` (FK `user.id`) — `src/identity/model.py`.
- `ProjectRole(StrEnum)`, `Project`, `ProjectMember` (PK `(project_id, user_id)`) — `src/features/projects/model.py`.
- `Table` (`__tablename__="projecttable"`, FKs `project.id`, `datastore.name`) — `src/features/tables/model.py`.
- `Blob` (FKs `project.id`, `datastore.name`) — `src/features/blobs/model.py`.
- `DataStoreVisibility(StrEnum)`, `DataStoreImplementationColumn(TypeDecorator)`, `DataStore`,
  `DataStoreImplementations` union, `PERSISTING` — `src/features/datastores/model.py`.

### Backend — storage contracts
- `src/features/datastores/storage.py`: `DataType(StrEnum)`, `namespace_of`, `DataStoreQuery`, `DataStoreQueryResponse`.
- `src/features/tables/storage.py`: `validate_identifier`, `QueryPrivilege` (READ_ONLY/READ_WRITE),
  `ColumnDefinition` (`name`, `type`, `nullable`, `primary_key`), `primary_key_of`, `TableStorage` Protocol.
- `src/features/blobs/storage.py`: `validate_object_key`, `BlobOperation`, `BlobDescription`,
  `PresignedAccess`, `BlobStorage` Protocol.
- Implementations: `DataStoreImplementationBase(BaseModel, ABC)` (`base.py`), `SQLiteDataStore`
  (`sqlite.py`), `MinIODataStore` (`minio.py`; `secret_key: SecretStr`, `presigned_url_expiry_seconds`),
  `_sqlite_privileges.py` (`Authorizer`, action sets; default DENY).

### Backend — runtime / API models
- `OpaPolicyDecisionPoint` (`src/authz/opa.py`), `AccessEnforcer` (`src/authz/enforcement.py`),
  `ApplicationServices` (`src/platform/state.py`), `IssuedApiKey` (`src/identity/service.py`),
  `DataStoreCatalogueEntry` (`src/features/datastores/catalogue.py`), `api_key_scheme` (`src/identity/caller.py`).
- Request/response models: users `CurrentUserResponse`, `UserResponse`, `CreateUserRequest`,
  `CreateApiKeyRequest`, `ApiKeyResponse`, `IssuedApiKeyResponse`, `CreatedUserResponse`; projects
  `CreateProjectRequest`, `GrantMembershipRequest`, `ProjectMembershipResponse`; tables
  `CreateTableRequest` (validator `_check_primary_key` → 422), `TableQueryRequest`; blobs
  `CreateBlobRequest`, `BlobView`, `CreatedBlob`, `BlobAccessRequest`; datastores
  `CreateDataStoreRequest`, `UpdateDataStoreVisibilityRequest`.

### Backend — test fixtures (`backend/tests/conftest.py`)
`POLICY_DIRECTORY`, `MINIO_IMAGE = "quay.io/minio/minio:latest"`, `POSTGRES_IMAGE = "postgres:18"`,
`TEST_DATABASE_VARIABLE = "TEST_DATABASE_URL"`, `CALLERS` (alice, bob, root), `MinIOServer` dataclass.

### Frontend
- `server/routes.ts`: `interface ProxyRoute { prefix; target; host? }`.
- `server/serve.ts` (module-level): `port`, `root`, `routes`, `HOP_BY_HOP`, `SECURITY_HEADERS`,
  `IMMUTABLE`, `REVALIDATE`, `COMPRESSIBLE`, `gzipped` (Map cache), `server`.
- `src/lib/authz.ts`: `type Permission` (15 literals matching Rego), role ladders,
  `ROLE_PERMISSIONS`, `interface Rights { role; can; mayGrant; mayRemove; refusal }`.
- `src/lib/api.ts`: `Uuid`, `ProjectRole`, `DataType`, `CurrentUser`, `Project`, `Membership`,
  `CatalogueEntry`, `Table`, `ColumnDefinition` (with `primary_key`), `QueryResponse`, `Blob`,
  `StoredBlob`, `BlobView`, `PresignedAccess`, `CreatedBlob`, `class ApiError` (`status`, 0 = unreachable), `const api`.
- `src/App.tsx`: `Selection` (`workspace|members|table|blob`), `Buffer`, `WorkspaceData`, `Overlay`
  union, `Confirm`, `KEY_STORE = "dataplatform.key"`.
- `components/Shell.tsx`: `Tab`, `Mode`, `SIGIL`. `components/Rail.tsx`: `RailRow`.
  `components/Palette.tsx`: `PaletteItem`. `components/TablePane.tsx`: `TableActions`.
  `components/dialogs.tsx`: `ROLES`, `DraftColumn`, `StepState`.
- `src/viewers/viewer.ts`: `ViewerProps`, `ThumbProps`, `Viewer`. Viewer consts: `image`, `video`,
  `audio`, `pdf`, `html`, `markdown`, `text`, `unknown` (fallback). Registry order (load-bearing):
  `image, video, audio, pdf, html, markdown, text`.
- `viewers/Transport.tsx`: `Playback`, `IDLE`. `lib/text.ts`: `TEXT_LIMIT` (1 MB), `TooLarge`,
  `Source`. `lib/tree.ts`: `Branch`, `Leaf`, `Node`, `Run` (private `Draft`). `lib/format.ts`:
  `ROW_LIMIT = 200`. `lib/media.ts`: private `held`, `MARGIN_MS`. `viewers/Pdf.tsx`: `INLINE_LIMIT` (32 MB).

## Functions

### Backend

| Function | Path |
|---|---|
| `main()`, `app` | `backend/main.py` |
| `create_app(*, config)`, `lifespan`, `GET /` `default()` | `backend/src/app.py` |
| `load_config(*, path)`, `DatabaseConfig._check_url_is_postgresql`, `AuthConfig._check_admins_are_distinct` | `backend/src/platform/config.py` |
| `configuration_path()`, `load_configuration()` | `backend/src/platform/environment.py` |
| `register_error_handlers(*, app)` with 11 handlers: `_handle_invalid_api_key` 401, `_handle_permission_denied` 403, `_handle_policy_engine_down` 503, `_handle_not_found` 404, `_handle_duplicate` 409, `_handle_in_use` 409, `_handle_query_refused` 403, `_handle_query_failed` 400, `_handle_unsuitable_datastore` 400, `_handle_blob_provisioning_failure` 502, `_handle_provisioning_failure` 400 | `backend/src/platform/error_handlers.py` |
| `get_services`, `get_session`, `get_enforcer`, `get_configuration` | `backend/src/platform/dependencies.py` |
| `create_database_engine`, `open_session` | `backend/src/database/engine.py` |
| `upgrade_to_head(*, engine)`, `_alembic_configuration(*, connection)` | `backend/src/database/migrations.py` |
| `_database_url`, `_run`, `run_migrations_offline`, `run_migrations_online` | `backend/migrations/env.py` |
| `generate_key`, `digest_of` | `backend/src/identity/keys.py` |
| `current_user`, `current_subject` | `backend/src/identity/caller.py` |
| `issue_api_key`, `authenticate`, `_is_usable`, `list_api_keys`, `revoke_api_key` | `backend/src/identity/service.py` |
| `ensure_bootstrap_admins`, `_ensure_administrator`, `_ensure_key`, `_ensure_key_is_still_theirs` | `backend/src/identity/bootstrap.py` |
| `OpaPolicyDecisionPoint.decide/filter_allowed/check_reachable` | `backend/src/authz/opa.py` |
| `AccessEnforcer.ensure_allowed/is_allowed/keep_allowed` | `backend/src/authz/enforcement.py` |
| `create_user`, `get_user`, `locate_user_by_email`, `find_user_by_email`, `list_users`, `describe_subject` | `backend/src/features/users/service.py` |
| `create_project`, `get_project`, `list_projects`, `roles_of_user`, `member_role`, `set_member_role`, `remove_member`, `list_members` | `backend/src/features/projects/service.py` |
| `_storage_behind`, `get_table`, `list_tables`, `create_table`, `delete_table`, `run_query` | `backend/src/features/tables/service.py` |
| `_storage_behind`, `get_blob`, `list_blobs`, `create_blob`, `describe_blob`, `grant_access`, `delete_blob` | `backend/src/features/blobs/service.py` |
| `create_datastore`, `get_datastore`, `list_datastores(visibility=)`, `set_visibility`, `delete_datastore` (catches `IntegrityError` → rollback → `ObjectInUseError`), `run_query` | `backend/src/features/datastores/service.py` |
| `_describe`, `list_catalogue` | `backend/src/features/datastores/catalogue.py` |
| `build_authorizer`, `is_refusal` | `backend/src/features/datastores/implementations/_sqlite_privileges.py` |
| `SQLiteDataStore.get_data_type/query/create_table/drop_table/query_table` | `.../implementations/sqlite.py` |
| `_unreachable`, `MinIODataStore.get_data_type/query/ensure_namespace/delete_blob/describe_blob/presign` | `.../implementations/minio.py` |
| `validate_identifier`, `primary_key_of` | `backend/src/features/tables/storage.py` |
| `validate_object_key` | `backend/src/features/blobs/storage.py` |
| `namespace_of` | `backend/src/features/datastores/storage.py` |
| `create_{users,projects,tables,blobs,datastores}_router`, each with `_as_resource`; users also `_describe_key`, `_describe_issued_key`, `_describe_user` | `backend/src/features/*/router.py` |
| Fixtures: `opa_url`, `minio_server`, `other_minio_server`, `postgres_server`, `database_url` (per-test DB), `config`, `engine`, `session`, `callers`, `client`; helpers `api_key_for`, `_free_port`, `_wait_until_ready`, `_running_minio`, `headers_for`, `user_id_of`, `make_platform_admin` | `backend/tests/conftest.py` |
| `register()` shell function | `backend/bootstrap.sh` |

### Rego — `backend/policies/dataplatform/authz.rego`
Permission sets `viewer ⊂ editor ⊂ admin ⊂ owner`, `role_permissions`; `default allow := false`;
`decision := {allow, reason}`; `allowed_resource_ids`; `is_allowed` (platform admin bypass, else
project role); `membership_change_forbidden` (only owner creates owner; owner never lowered/removed).

### Frontend

| Function / component | Path |
|---|---|
| `proxyRoutes(env = process.env): ProxyRoute[]` | `frontend/server/routes.ts` |
| `routeFor(pathname)`, `forward(request, route, client)`, `gzipOf(path)`, `fileAt(pathname)`, `serveStatic(request)`, `Bun.serve({fetch, error})`, SIGTERM/SIGINT handlers | `frontend/server/serve.ts` |
| `asViteProxy(route)` | `frontend/vite.config.ts` |
| `rightsIn(me, project)`, private `changeForbidden` | `frontend/src/lib/authz.ts` |
| `setKey`, `call`, `readDetail`, `keyPath`, `viaProxy`, `uploadTo`; `api.me/listProjects/createProject/listMembers/grantMembership/removeMembership/catalogue/listTables/createTable/deleteTable/query/listBlobs/readBlob/createBlob/deleteBlob/blobAccess` | `frontend/src/lib/api.ts` |
| `isIdentifier`, `literal`, `insertStatement`, `addColumnStatement`, `selectStatement`, `createTableSketch`, `verbOf`, `isRead` | `frontend/src/lib/sql.ts` |
| `build`, `flatten`, `branchPaths`, `ancestors`, `runs` (private `draft`, `keptUnder`) | `frontend/src/lib/tree.ts` |
| `downloadUrl`, `forget` | `frontend/src/lib/media.ts` |
| `bytes`, `latency`, `stamp`, `clock`, `timecode` | `frontend/src/lib/format.ts` |
| `readSource` | `frontend/src/lib/text.ts` |
| `App()` — all state, single `keydown` dispatcher, `commands` registry (`:new workspace`, `:new table`, `:upload`, `:add column`, `:insert row`, `:find`, `:new tab`, `:close`, `:grant access`, `:members`, `:reload`, `:density`, `:gloss`, `:forget key`) | `frontend/src/App.tsx` |
| `Tabline`, `Cmdline`, `Statusline`, `Canvas` (+ `WorkspaceSegment`) | `frontend/src/components/Shell.tsx` |
| `railRows`, `Rail` (+ `isPage`, `Name`) | `frontend/src/components/Rail.tsx` |
| `WorkspacePane`, `MembersPane`, `TablePane`, `BlobPane`, `ContactSheet`, `Gate`, `Palette` | `frontend/src/components/*.tsx` |
| `NewWorkspaceDialog`, `GrantDialog`, `NewTableDialog`, `AddColumnDialog`, `InsertRowDialog`, `UploadDialog`, `ConfirmDialog` | `frontend/src/components/dialogs.tsx` |
| `Dialog`, `Modal` (+ `useOverlay`) | `frontend/src/components/Overlay.tsx` |
| `Head`, `Empty`, `Loading`, `Problem`, `Field`, `Sketch`, `KV`, `Fact` | `frontend/src/components/bits.tsx` |
| `claimsType`, `claimsName` | `frontend/src/viewers/viewer.ts` |
| `resolve(contentType, key)` | `frontend/src/viewers/registry.ts` |
| `Frame`, `Undecodable` | `frontend/src/viewers/Frame.tsx` |
| `useTransport`, `Transport` | `frontend/src/viewers/Transport.tsx` |

### HTTP surface (backend)
- `GET /` (health).
- Users: `GET /users/me`, `POST|GET /users/me/api-keys`, `DELETE /users/me/api-keys/{key_id}`,
  `POST /users/`, `GET /users/`, `POST /users/{user_id}/api-keys`.
- Projects: `POST /projects/`, `GET /projects/`, `GET /projects/{id}`, `GET|PUT /projects/{id}/members`,
  `DELETE /projects/{id}/members/{user_id}`.
- Tables (`/projects/{project_id}/tables`): `POST /`, `GET /`, `GET /{table_name}`,
  `POST /{table_name}/query`, `DELETE /{table_name}`.
- Blobs (`/projects/{project_id}/blobs`): `POST /`, `GET /?prefix=`, `GET /{key:path}`,
  `POST /{key:path}/access`, `DELETE /{key:path}`.
- Datastores: `GET /datastores/query`, `GET /datastores/catalogue`, `POST /datastores/`,
  `GET /datastores/`, `GET|PATCH|DELETE /datastores/{name}` (DELETE → 409 if still referenced).
- Console reaches all of this as `/api/...` (prefix stripped by Vite or `serve.ts`); signed blob
  URLs as `/blob/...`.

## Dependencies

### Backend (`backend/pyproject.toml`, Python ≥3.14, uv)
- **alembic** ≥1.19.1, **email-validator** ≥2.3.0, **fastapi** ≥0.136.3, **httpx** ≥0.28.1 (OPA
  client), **loguru** ≥0.7.3, **minio** ≥7.2.20, **psycopg[binary]** ≥3.2 (Postgres driver),
  **pydantic** ≥2.13.4, **pyyaml** ≥6.0.3, **sqlmodel** ≥0.0.38 (+SQLAlchemy), **urllib3** ≥2.7.0.
- stdlib: `sqlite3` (authorizer API), `secrets`, `hashlib`, `asyncio.to_thread`.
- Dev: `fastapi[standard]`, `pytest` ≥9.1.1, `pytest-asyncio` ≥1.4, `pytest-cov` ≥7.1
  (`fail_under=80`, branch), `ruff` ≥0.16.3 (line 96, py314), `ty` ≥0.0.39.

### Frontend (`frontend/package.json`)
- Runtime: **react** ^19.1, **react-dom** ^19.1 only.
- Dev: **vite** ^7, **@vitejs/plugin-react** ^5, **typescript** ^5.7, `@types/node` ^26.2,
  `@types/react` ^19.1, `@types/react-dom` ^19.1. Build: `tsc -b && vite build`.
- Image runtime: **Bun 1.4.2** (`oven/bun:1.4.2-slim` build, `oven/bun:1.4.2-distroless` run);
  `serve.ts` uses only Bun built-ins (`Bun.serve`, `Bun.file`, `Bun.gzipSync`) and `node:path`.
- Browser APIs: `fetch`/`AbortController`, `TextDecoder`, object URLs, media elements, Fullscreen,
  `localStorage`, `DataTransfer`.

### External services / tooling
- **PostgreSQL** (`postgres:18`) — metadata DB, required; tests start a container or use `TEST_DATABASE_URL`.
- **Open Policy Agent** (`openpolicyagent/opa:1.19.0` or local `opa`) — required; paths
  `dataplatform/authz/decision` and `dataplatform/authz/allowed_resource_ids`.
- **MinIO** — compose uses `cgr.dev/chainguard/minio`; tests use local `minio` binary or
  `quay.io/minio/minio:latest`, running two servers.
- **SQLite** files for table datastores (`/data/sqlite/*.db` in compose).
- **Docker Compose** (root file), `curlimages/curl` for bootstrap, uv base image for backend.
- No external identity provider.

## Notable design notes / gotchas

- **Config env var is `DATAPLATFORM_CONFIG`** (default `./config.yaml`). Compose sidesteps it by
  mounting the inline config at `/app/config.yaml`. (An earlier uncommitted rename to `CONFIG`
  was never committed.)
- **Remaining docs drift:** `frontend/README.md` "Running it" (`cd ../backend && docker compose
  up -d`); `bootstrap.sh` defaults (`http://api:8000`, `/config.docker.yaml`, `seed:` log prefix)
  — harmless since compose sets `API_URL`/`CONFIG_FILE`.
- **Blob proxy / signatures:** the API signs URLs for `minio:9000`; whichever server fronts the
  console must forward `/blob` to where MinIO is reachable while sending `Host: minio:9000`, and
  must keep path+query byte-identical (re-encoding `+`/`%2F` breaks the signature). Vite: set Host
  in proxy options, not `proxyReq` (Expect: 100-continue). From the host shell use
  `curl --resolve minio:9000:127.0.0.1`.
- **`serve.ts`** logs path only (query of `/blob` is a credential); `X-Frame-Options: SAMEORIGIN`
  (not DENY) because the pdf viewer frames `/blob`; missing `/assets/*` → 404 instead of SPA fallback.
- Backend container copies source (no bind mount): `docker compose up -d --build backend`.
- **Deleting a datastore** relies on FKs from `projecttable`/`blob` to `datastore.name`;
  `IntegrityError` → `ObjectInUseError` (409).
- **Migrations** run at startup via `upgrade_to_head` inside `engine.begin()`; revisions are
  PostgreSQL-only (quote `"user"`, create `sa.Enum` types with `checkfirst=True` before
  `add_column`). Autogenerate renders `DataStoreImplementationColumn()` — replace with `sa.JSON()`.
- **Layout rules:** a feature owns its storage protocol; no `__init__.py` re-exports;
  `platform`/`database` know nothing about features; only crossings are `identity → features.users`
  and `authz → features.projects.model`; only `src/app.py` names OPA.
- **Ask the policy before the database** so refusals do not reveal existence. `POST /projects/`
  has no enforcer call; `/users/me/...` key endpoints are not put to the policy;
  `GET /datastores/catalogue` open to every authenticated caller; `visibility` hides but never protects.
- Table query: `table.write` asked via `is_allowed`, else `table.query` enforced; picks
  `QueryPrivilege`. Primary key: marked columns form one key; nullable key → 422.
- MinIO `secret_key` is `SecretStr` revealed only when persisting. Presigned URLs ≤15 min.
- **Frontend:** `lib/authz.ts` must be kept rung-for-rung with `authz.rego`. Tabs are buffers;
  one keydown dispatcher, one command registry. Table shape read with `SELECT * ... LIMIT 0`.
  HTML blobs shown as source only. `--vg-fg-muted` overridden in `app.css` for contrast.
- **Exploration gotchas:** globbing `backend/` unqualified is dominated by `.venv` — glob
  `backend/src/**/*.py`, `backend/tests/*.py`. Root glob also lists nested `agent-knowledge` and
  `.claude` folders.
