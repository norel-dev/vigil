# Vigil — data platform monorepo (`backend/` FastAPI API + `frontend/` React console)

> **This file is the canonical report.** It lives at the repository root because the
> explorer now runs from `/Users/norel/code/vigil`. Two older reports exist and are
> **stale** (they describe the previous layout `/Users/norel/dataplatform/app/...` at `7e30d98`):
> `backend/agent-knowledge/repository-explorer/CODEBASE.MD` (also carries uncommitted user
> edits — not touched) and `frontend/agent-knowledge/repository-explorer/CODEBASE.MD` (a pointer).

## Commit

- Repository root: **`/Users/norel/code/vigil`** (single git repo). The code moved from
  `app/backend` + `app/frontend` to **`backend/`** + **`frontend/`** at the root; the
  `chart/` Helm directory of the old repo is **gone**.
- Branch: **`main`**. HEAD: **`65c022b`** — "feat: add frontend dockeradd frontend dockerfile".
  - `532c63a` — "fix: minio new deployment (support removed for ce)" (MinIO image switched to
    `cgr.dev/chainguard/minio` in compose)
  - `9cca81a` — "update codebase.md"
  - `7e30d98` — "State a key column's NOT NULL as a fact instead of a greyed-out toggle"
  - `eff821a` — "Let a table's primary key be asked for by marking its columns in the console"
  - earlier: `f3833a6` (backend primary keys), `ee639a5` (members page), `69455d2`, `bbf80d9`,
    `8f4094c`, `1d3c9ac`, `86127f2`, `539fdb9`, `7386e5d`, `ec9adb9`, `8485acc`.
- **Uncommitted working tree at time of writing (important — this report describes it):**
  - NEW root `README.md` (project named **Vigil**), NEW root **`docker-compose.yaml`**, NEW
    **`backend/bootstrap.sh`** (replaces the deleted `backend/scripts/seed-datastores.sh`).
  - DELETED `backend/docker-compose.yaml`, `backend/config.docker.yaml`,
    `backend/config.example.yaml`.
  - MODIFIED: `backend/Dockerfile`, `backend/README.md`, `backend/pyproject.toml`, `uv.lock`,
    `migrations/env.py`, `0004_api_keys.py`, `0006_datastore_visibility.py`,
    `src/database/migrations.py`, `src/features/datastores/service.py`,
    `src/platform/{config,environment,error_handlers,exceptions}.py`, and tests
    `conftest.py`, `test_api_keys`, `test_configuration`, `test_datastore_persistence`,
    `test_enforcement`, `test_migrations`, `test_table_access`.
  - Net effect: metadata DB is **PostgreSQL only** (psycopg), config env var renamed
    `DATAPLATFORM_CONFIG` → **`CONFIG`**, new **`ObjectInUseError` → 409** when deleting a
    datastore that tables/blobs still reference, compose consolidated at the root.

## Description

Vigil ("a simple and modular data platform designed to abstractly accommodate any query engine
and blob store") is two applications:

1. **`backend/` — the API.** Python **3.14** + FastAPI (pyproject name `api`, description
   "API for the Project Arcanist dataplatform"). Abstracts management of data held across
   several underlying stores (SQLite for tables, MinIO/S3 for blobs). Authentication by **API
   keys the platform issues itself** (`dpk_…`, stored only as a SHA-256 digest). Authorization
   delegated wholesale to an **Open Policy Agent** Rego policy; fails **closed** (503) if OPA is
   unreachable. Metadata DB is **PostgreSQL** (`postgresql+psycopg://` only), schema owned by
   **Alembic** revisions applied automatically at startup. ~52 Python modules under `src/` +
   `main.py`; 17 `test_*.py` + `conftest.py`; 6 migrations + `env.py`; 2 Rego files.
2. **`frontend/` — the console.** React 19 + TypeScript + Vite SPA (`"name":
   "dataplatform-console"`). Keyboard-first, vim/Neovim-flavoured UI: blobs (upload + view
   image/video/audio/pdf/html/markdown/text), tables (create with primary key, add columns,
   insert rows, run SQL), workspaces (= projects) with membership on its own page. 34 source
   files under `src/`: 7 `lib` modules, 12 components, 10 viewers, `App.tsx`, `main.tsx`,
   3 CSS files. Runtime deps: only `react` and `react-dom`. Has a **Dockerfile on Bun**
   (`oven/bun:1.4.2-slim`) running Vite's dev server.

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
  offering refused acts; a workspace's contents and its access are two pages.

Entrypoints: whole stack `docker compose up -d` **from the repo root**; backend alone
`uv run fastapi dev main.py` (in `backend/`); frontend `npm run dev` → `http://localhost:5173`.

## File Structure

| Path | Description | Usage frequency |
|---|---|---|
| `/Users/norel/code/vigil/` | Repo root: `README.md` (Vigil intro, uncommitted), `docker-compose.yaml` (uncommitted), `backend/`, `frontend/`, `agent-knowledge/` (this report). No root `.gitignore`. | rare |
| `docker-compose.yaml` (root) | **Dev stack.** `x-config` anchors for creds/ports; an inline compose `configs.backend_config` YAML (mounted at `/app/config.yaml` in backend and `/config.yaml` in bootstrap) — DB `postgresql+psycopg://postgres:password@postgres:5432/postgres` by default, bootstrap admin `root@example.com` with `BOOTSTRAP_API_KEY` (default `dpk_local_docker_compose_development_key`), OPA `http://opa:8181`. Services: `backend` (container `vigil-backend`, build `backend/`, volume `sqlite_data:/data/sqlite`), `opa` (`openpolicyagent/opa:1.19.0`, mounts `./backend/policies`), `minio` (`cgr.dev/chainguard/minio`, 9000 + console 9001, healthcheck `mc ready local`), `postgres` (`postgres:18`), `bootstrap` (`curlimages/curl:8.11.1`, runs `backend/bootstrap.sh` once). Volumes `postgres_data`, `sqlite_data`, `minio_data`. Ports overridable via `BACKEND_PORT`, `OPA_PORT`, `MINIO_PORT`, `MINIO_CONSOLE_PORT`, `POSTGRES_PORT`. **No frontend service yet**, and no source bind-mount for backend. | dev |
| `backend/` | The API project (uv-managed). | constant |
| `backend/main.py` | Entry: `main()` loads config via `src.platform.environment`, builds app, module-level `app`; exits 1 on `ConfigurationError` (its hint still mentions `config.example.yaml`, which is deleted). | on start |
| `backend/bootstrap.sh` | POSIX sh "administrator": reads `api_key` out of `$CONFIG_FILE` via `sed`, waits for `$API_URL/`, idempotently registers `sqlite-main` (`/data/sqlite/main.db`), `sqlite-scratch` (`/data/sqlite/scratch.db`), `minio-blobs` (endpoint `$MINIO_ENDPOINT`, root creds, `secure:false`, expiry 900). Defaults still name `http://api:8000` and `/config.docker.yaml`, overridden by compose env. | dev |
| `backend/Dockerfile` | `ghcr.io/astral-sh/uv:python3.14-bookworm-slim`, venv at `/opt/venv`, `uv sync --frozen --no-install-project`, copies source, `HEALTHCHECK` on `/`, `CMD fastapi dev main.py --host 0.0.0.0 --port 8000`. | dev |
| `backend/.dockerignore`, `.gitignore`, `.python-version` | Ignore lists (excludes `config.yaml`); Python version pin. | setup |
| `backend/README.md` | Access model, catalogue, visibility, tables & privileges, primary keys, blobs & signed URLs, running, keys, migrations, tests, layout. **Best single doc on the backend, but its "Running it" section is stale**: mentions `config.docker.yaml`, `config.example.yaml`, `seed` container, `api` service, `API_PORT`, `DATAPLATFORM_CONFIG`, `/data/stores/*.db`, `dataplatform/dataplatform-secret` Postgres creds — all superseded by the root compose. | reference |
| `backend/pyproject.toml`, `uv.lock` | Deps, pytest/coverage/ruff settings. | setup |
| `backend/alembic.ini` | Alembic settings; deliberately no `sqlalchemy.url` (comment still says `DATAPLATFORM_CONFIG`). | migrations |
| `backend/migrations/` | `env.py`, `README`, `script.py.mako`, `versions/`: `0001_baseline`, `0002_system_level_datastores`, `0003_project_tables`, `0004_api_keys`, `0005_project_blobs`, `0006_datastore_visibility`. Revisions never import from `src`; written for PostgreSQL. | history |
| `backend/policies/dataplatform/` | `authz.rego`, `authz_test.rego` (`opa test policies -v`). Mounted into the OPA container. | every request |
| `backend/src/app.py` | `create_app` — wires OPA, mounts routers, lifespan (migrate, bootstrap admins). Only module naming OPA. | on start |
| `backend/src/features/` | One package per offering: `users/`, `projects/`, `tables/`, `blobs/`, `datastores/` — each `model.py`, `service.py`, `router.py` (+ `storage.py` where it owns a storage protocol; `datastores/catalogue.py`). | every request |
| `backend/src/features/datastores/implementations/` | `base.py`, `sqlite.py`, `minio.py`, `_sqlite_privileges.py`. | every request |
| `backend/src/identity/` | Who the caller is: `keys.py`, `model.py`, `service.py`, `caller.py`, `bootstrap.py`. | every request |
| `backend/src/authz/` | What the caller may do: `policy.py`, `opa.py`, `enforcement.py`. | every request |
| `backend/src/database/` | `engine.py`, `migrations.py`. Feature-agnostic. | on start |
| `backend/src/platform/` | Plumbing: `config.py`, `environment.py`, `exceptions.py`, `error_handlers.py`, `state.py`, `dependencies.py`. Feature-agnostic. | every request |
| `backend/tests/` | `conftest.py` + 17 test files: `test_api_keys`, `test_blob_access`, `test_blob_keys`, `test_blob_storage`, `test_bootstrap_admin`, `test_configuration`, `test_datastore_access`, `test_datastore_catalogue`, `test_datastore_persistence`, `test_datastore_visibility`, `test_enforcement`, `test_migrations`, `test_opa_client`, `test_project_access` (largest), `test_table_access`, `test_table_storage`, `test_user_administration`. | CI/dev |
| `backend/agent-knowledge/repository-explorer/` | Stale older report (see top). | never |
| `frontend/` | The console (npm/Vite; Docker image on Bun). | constant |
| `frontend/Dockerfile` (new in `65c022b`) | `oven/bun:1.4.2-slim`; `bun install` from `package.json`+`package-lock.json` into `/srv/node_modules`, source at `/srv/app` (designed to be bind-mounted read-only over), `VITE_CACHE_DIR=/srv/node_modules/.vite`, `CMD vite --host 0.0.0.0 --port 5173`, healthcheck via `bun -e fetch`. Notes: if large uploads fail with `SignatureDoesNotMatch`, Bun's proxy Host handling is the first suspect. | dev |
| `frontend/.dockerignore`, `.gitignore`, `index.html`, `tsconfig.json`, `package.json`, `package-lock.json` | Vite shell, strict TS config, scripts `dev`/`build`/`preview`. | dev |
| `frontend/vite.config.ts` | Two dev proxies: `/api` → `API_PROXY_TARGET` (default `http://127.0.0.1:8000`, `changeOrigin:true`), `/blob` → `BLOB_PROXY_TARGET` (default `http://127.0.0.1:9000`, `changeOrigin:false`, `headers:{Host:"minio:9000"}`). Also `cacheDir` from `VITE_CACHE_DIR`, polling watcher when `VITE_USE_POLLING=true`. | dev |
| `frontend/README.md` | Proxies, API assumptions, keyboard, buffers/workspaces, workspace pages, viewers, transport, blob tree, layout. **Stale bits:** says to `cd ../backend && docker compose up -d` and that the key is in `../backend/config.docker.yaml`. | reference |
| `frontend/src/lib/` | `api.ts`, `authz.ts`, `sql.ts`, `media.ts`, `format.ts`, `tree.ts`, `text.ts`. | every render |
| `frontend/src/viewers/` | `viewer.ts`, `registry.ts`, `Frame.tsx`, `Transport.tsx`, `Image.tsx`, `Video.tsx`, `Audio.tsx`, `Pdf.tsx`, `Source.tsx`, `Unknown.tsx`. | every blob render |
| `frontend/src/components/` | `Shell.tsx`, `Rail.tsx`, `WorkspacePane.tsx`, `MembersPane.tsx`, `TablePane.tsx`, `BlobPane.tsx`, `ContactSheet.tsx`, `dialogs.tsx`, `Overlay.tsx`, `Palette.tsx`, `Gate.tsx`, `bits.tsx`. | every render |
| `frontend/src/vigil/` | The **Vigil** design system vendored (`tokens.css`, `components.css`) + console layer `app.css` (`dp-` prefixed). `main.tsx` must import `app.css` **after** `components.css`. | every render |
| `frontend/public/` | `mark.svg`, `favicon.svg`. | rare |
| `frontend/design/` | Not present in this checkout (was gitignored design handoff). | never |
| `backend/.venv/`, `frontend/node_modules/`, `**/__pycache__/` | Thousands of files; ignore. | never |

## Objects

### Backend — configuration (`backend/src/platform/config.py`, `environment.py`)
- `MINIMUM_BOOTSTRAP_KEY_LENGTH = 32`; **`METADATA_DATABASE_DRIVER = "postgresql+psycopg"`**.
- `DatabaseConfig` (`url`, `echo`; validator `_check_url_is_postgresql` — rejects any other
  driver via `sqlalchemy.make_url`), `BootstrapAdminConfig` (`email`, `name`, `api_key` ≥32),
  `AuthConfig` (`bootstrap_platform_admins`; `_check_admins_are_distinct`), `OpaConfig`
  (`url`, `decision_path`, `filter_path`, `request_timeout_seconds`), `AppConfig`.
- `environment.py`: **`CONFIG_PATH_VARIABLE = "CONFIG"`**, `DEFAULT_CONFIG_PATH = Path("config.yaml")`.

### Backend — exceptions (`backend/src/platform/exceptions.py`)
`DataPlatformError` → `ConfigurationError`, `SchemaMigrationError`, `ObjectNotFoundError`,
`DuplicateObjectError`, **`ObjectInUseError`** (new), `AuthenticationError`→`InvalidApiKeyError`,
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
  `ColumnDefinition` (`name`, `type`, `nullable`, `primary_key`), `primary_key_of` (key columns
  may not be nullable → `ValueError`), `TableStorage` Protocol.
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
- `src/lib/authz.ts`: `type Permission` (15 literals matching Rego), role ladders,
  `ROLE_PERMISSIONS`, `interface Rights { role; can; mayGrant; mayRemove; refusal }`.
- `src/lib/api.ts`: `Uuid`, `ProjectRole`, `DataType`, `CurrentUser`, `Project`, `Membership`,
  `CatalogueEntry`, `Table`, `ColumnDefinition` (with `primary_key`), `QueryResponse`, `Blob`,
  `StoredBlob`, `BlobView`, `PresignedAccess`, `CreatedBlob`, `class ApiError` (`status`, 0 = unreachable), `const api`.
- `src/App.tsx`: `Selection` (`workspace|members|table|blob`), `Buffer`, `WorkspaceData`, `Overlay`
  union, `Confirm`, `KEY_STORE = "dataplatform.key"`.
- `components/Shell.tsx`: `Tab` (`workspace|members|table|blob`), `Mode`, `SIGIL`.
  `components/Rail.tsx`: `RailRow`. `components/Palette.tsx`: `PaletteItem`.
  `components/TablePane.tsx`: `TableActions`. `components/dialogs.tsx`: `ROLES`, `DraftColumn`, `StepState`.
- `src/viewers/viewer.ts`: `ViewerProps`, `ThumbProps`, `Viewer`. Viewer consts: `image`, `video`,
  `audio`, `pdf`, `html`, `markdown`, `text`, `unknown` (fallback). Registry order (load-bearing):
  `image, video, audio, pdf, html, markdown, text`.
- `viewers/Transport.tsx`: `Playback`, `IDLE`. `lib/text.ts`: `TEXT_LIMIT` (1 MB), `TooLarge`,
  `Source`. `lib/tree.ts`: `Branch`, `Leaf`, `Node`, `Run`. `lib/format.ts`: `ROW_LIMIT = 200`.
  `viewers/Pdf.tsx`: `INLINE_LIMIT` (32 MB).

## Functions

### Backend

| Function | Path |
|---|---|
| `main()`, `app` | `backend/main.py` |
| `create_app(*, config)`, `lifespan`, `GET /` `default()` | `backend/src/app.py` |
| `load_config(*, path)`, `DatabaseConfig._check_url_is_postgresql`, `AuthConfig._check_admins_are_distinct` | `backend/src/platform/config.py` |
| `configuration_path()`, `load_configuration()` | `backend/src/platform/environment.py` |
| `register_error_handlers(*, app)` with 11 handlers: `_handle_invalid_api_key` 401, `_handle_permission_denied` 403, `_handle_policy_engine_down` 503, `_handle_not_found` 404, `_handle_duplicate` 409, **`_handle_in_use` 409**, `_handle_query_refused` 403, `_handle_query_failed` 400, `_handle_unsuitable_datastore` 400, `_handle_blob_provisioning_failure` 502, `_handle_provisioning_failure` 400 | `backend/src/platform/error_handlers.py` |
| `get_services`, `get_session`, `get_enforcer`, `get_configuration` | `backend/src/platform/dependencies.py` |
| `create_database_engine`, `open_session` | `backend/src/database/engine.py` |
| `upgrade_to_head(*, engine)`, `_alembic_configuration(*, connection)`; `_ALEMBIC_CONFIGURATION` = `parents[2]/alembic.ini` | `backend/src/database/migrations.py` |
| `_database_url`, `_run`, `run_migrations_offline`, `run_migrations_online` (borrows `config.attributes["connection"]`; honours `configure_logger`) | `backend/migrations/env.py` |
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
| `create_datastore`, `get_datastore`, `list_datastores(visibility=)`, `set_visibility`, **`delete_datastore` (catches `IntegrityError` → rollback → `ObjectInUseError`)**, `run_query` | `backend/src/features/datastores/service.py` |
| `_describe`, `list_catalogue` | `backend/src/features/datastores/catalogue.py` |
| `build_authorizer`, `is_refusal` | `backend/src/features/datastores/implementations/_sqlite_privileges.py` |
| `SQLiteDataStore.get_data_type/query/create_table/drop_table/query_table` | `.../implementations/sqlite.py` |
| `_unreachable`, `MinIODataStore.get_data_type/query/ensure_namespace/delete_blob/describe_blob/presign` | `.../implementations/minio.py` |
| `validate_identifier`, `primary_key_of` | `backend/src/features/tables/storage.py` |
| `validate_object_key` | `backend/src/features/blobs/storage.py` |
| `namespace_of` | `backend/src/features/datastores/storage.py` |
| `create_{users,projects,tables,blobs,datastores}_router`, each with `_as_resource`; users also `_describe_key`, `_describe_issued_key`, `_describe_user` | `backend/src/features/*/router.py` |
| Fixtures: `opa_url`, `minio_server`, `other_minio_server`, `postgres_server`, `database_url` (per-test `CREATE DATABASE`/`DROP ... WITH (FORCE)`), `config`, `engine`, `session`, `callers`, `client`; helpers `api_key_for`, `_free_port`, `_wait_until_ready`, `_running_minio`, `headers_for`, `user_id_of`, `make_platform_admin` | `backend/tests/conftest.py` |
| `register()` shell function | `backend/bootstrap.sh` |

### Rego — `backend/policies/dataplatform/authz.rego`
Permission sets `viewer ⊂ editor ⊂ admin ⊂ owner`, `role_permissions`; `default allow := false`;
`decision := {allow, reason}` with six reasons; `allowed_resource_ids`; `is_allowed` (platform
admin bypass, else project role); `membership_change_forbidden` (only owner creates owner; owner
never lowered/removed).

### Frontend

| Function / component | Path |
|---|---|
| `rightsIn(me, project: Uuid \| null)`, private `changeForbidden` | `frontend/src/lib/authz.ts` |
| `setKey`, `call`, `readDetail`, `keyPath`, `viaProxy`, `uploadTo`; `api.me/listProjects/createProject/listMembers/grantMembership/removeMembership/catalogue/listTables/createTable/deleteTable/query/listBlobs/readBlob/createBlob/deleteBlob/blobAccess` | `frontend/src/lib/api.ts` |
| `isIdentifier`, `literal`, `insertStatement`, `addColumnStatement`, `selectStatement`, `createTableSketch` (emits `PRIMARY KEY (…)`), `verbOf`, `isRead` | `frontend/src/lib/sql.ts` |
| `build`, `flatten`, `branchPaths`, `ancestors`, `runs` | `frontend/src/lib/tree.ts` |
| `downloadUrl`, `forget` | `frontend/src/lib/media.ts` |
| `bytes`, `latency`, `stamp`, `clock`, `timecode` | `frontend/src/lib/format.ts` |
| `readSource` | `frontend/src/lib/text.ts` |
| `App()` — all state, single `keydown` dispatcher, `commands` registry (`:new workspace`, `:new table`, `:upload`, `:add column`, `:insert row`, `:find`, `:new tab`, `:close`, `:grant access`, `:members`, `:reload`, `:density`, `:gloss`, `:forget key`) | `frontend/src/App.tsx` |
| `Tabline`, `Cmdline`, `Statusline`, `Canvas` (+ internal `WorkspaceSegment`) | `frontend/src/components/Shell.tsx` |
| `railRows`, `Rail` (+ private `isPage`, `Name`) | `frontend/src/components/Rail.tsx` |
| `WorkspacePane`, `MembersPane`, `TablePane`, `BlobPane`, `ContactSheet`, `Gate`, `Palette` | `frontend/src/components/*.tsx` |
| `NewWorkspaceDialog`, `GrantDialog`, `NewTableDialog` (per-column `key` toggle; key columns show a `not null` tag), `AddColumnDialog`, `InsertRowDialog`, `UploadDialog`, `ConfirmDialog` | `frontend/src/components/dialogs.tsx` |
| `Dialog`, `Modal` (+ `useOverlay`) | `frontend/src/components/Overlay.tsx` |
| `Head`, `Empty`, `Loading`, `Problem`, `Field`, `Sketch`, `KV`, `Fact` | `frontend/src/components/bits.tsx` |
| `claimsType`, `claimsName` | `frontend/src/viewers/viewer.ts` |
| `resolve(contentType, key)` | `frontend/src/viewers/registry.ts` |
| `Frame`, `Undecodable` | `frontend/src/viewers/Frame.tsx` |
| `useTransport`, `Transport` | `frontend/src/viewers/Transport.tsx` |

### HTTP surface
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
  `GET /datastores/`, `GET|PATCH|DELETE /datastores/{name}` (DELETE → **409** if still referenced).

## Dependencies

### Backend (`backend/pyproject.toml`, Python ≥3.14, uv)
- **alembic** ≥1.19.1 (migrations), **email-validator** ≥2.3.0, **fastapi** ≥0.136.3, **httpx**
  ≥0.28.1 (OPA client), **loguru** ≥0.7.3, **minio** ≥7.2.20 (blob store client),
  **psycopg[binary]** ≥3.2 (new — the PostgreSQL driver), **pydantic** ≥2.13.4, **pyyaml** ≥6.0.3,
  **sqlmodel** ≥0.0.38 (+SQLAlchemy), **urllib3** ≥2.7.0 (named explicitly for MinIO's `HTTPError`).
- stdlib: `sqlite3` (authorizer API), `secrets`, `hashlib`, `asyncio.to_thread`.
- Dev: `fastapi[standard]`, `pytest` ≥9.1.1, `pytest-asyncio` ≥1.4 (auto), `pytest-cov` ≥7.1
  (`fail_under=80`, branch), `ruff` ≥0.16.3 (`E,F,W,I,UP,B,SIM,RET,C4,S`, line 96, py314), `ty` ≥0.0.39.

### Frontend (`frontend/package.json`)
- Runtime: **react** ^19.1, **react-dom** ^19.1 only.
- Dev: **vite** ^7, **@vitejs/plugin-react** ^5, **typescript** ^5.7, `@types/node` ^26.2,
  `@types/react` ^19.1, `@types/react-dom` ^19.1. Build: `tsc -b && vite build`.
- Container runtime: **Bun** 1.4.2 (no Node in the image).
- Browser APIs: `fetch`/`AbortController`, `TextDecoder`, object URLs, media elements, Fullscreen,
  `localStorage`, `DataTransfer`.

### External services / tooling
- **PostgreSQL** (`postgres:18`) — metadata DB, required; tests start a container or use `TEST_DATABASE_URL`.
- **Open Policy Agent** (`openpolicyagent/opa:1.19.0` or local `opa`) — required; paths
  `dataplatform/authz/decision` and `dataplatform/authz/allowed_resource_ids`.
- **MinIO** — compose uses `cgr.dev/chainguard/minio` (switched in `532c63a`); tests use a local
  `minio` binary or `quay.io/minio/minio:latest` via Docker, running **two** servers.
- **SQLite** files for table datastores (`/data/sqlite/*.db` in compose).
- **Docker Compose** (root file), **curl** image for bootstrap, **uv** base image for the backend.
- No external identity provider.

## Notable design notes / gotchas

- **Docs drift (current working tree):** `backend/README.md`, `frontend/README.md`,
  `backend/main.py`'s error hint, `backend/alembic.ini`'s comment and `bootstrap.sh`'s defaults
  still reference the deleted `config.docker.yaml` / `config.example.yaml`, the old `seed`/`api`
  service names, `API_PORT`, and `DATAPLATFORM_CONFIG`. The truth is: root `docker-compose.yaml`,
  services `backend`/`bootstrap`, env var `CONFIG`, port var `BACKEND_PORT`, Postgres
  `postgres`/`password`/`postgres` by default, SQLite files under `/data/sqlite`.
- **The root compose has no frontend service**, though `frontend/Dockerfile` and `vite.config.ts`
  (`API_PROXY_TARGET`, `BLOB_PROXY_TARGET`, `VITE_USE_POLLING`, `VITE_CACHE_DIR`) are ready for one.
- The backend container does **not** bind-mount source anymore (the old README's hot-reload note
  no longer holds); rebuild with `docker compose up -d --build backend`.
- **Deleting a datastore** relies on the FKs from `projecttable`/`blob` to `datastore.name`;
  `delete_datastore` turns the `IntegrityError` into `ObjectInUseError` (409, "still in use").
  Tested in `test_table_access.py`.
- **Migrations:** run at startup via `upgrade_to_head` inside `engine.begin()`; `env.py` borrows the
  passed connection and skips `fileConfig` when `configure_logger` is False. Revisions are
  PostgreSQL-only: quote `"user"`, create `sa.Enum` types with `.create(bind, checkfirst=True)`
  before `add_column` (see `0006`). Autogenerate renders the implementation column as
  `DataStoreImplementationColumn()` — replace with `sa.JSON()`.
- **Layout rules:** a feature owns its storage protocol; no `__init__.py` re-exports;
  `platform`/`database` know nothing about features; only crossings are `identity → features.users`
  and `authz → features.projects.model`; only `src/app.py` names OPA.
- **Ask the policy before the database** so refusals do not reveal existence. `POST /projects/`
  has no enforcer call; `/users/me/...` key endpoints are not put to the policy;
  `GET /datastores/catalogue` is open to every authenticated caller; `visibility` hides but
  never protects.
- Table query: `table.write` asked via `is_allowed`, else `table.query` enforced; picks
  `QueryPrivilege`. Primary key: columns marked `primary_key` form one key; nullable key → 422;
  SQLite emits a single `PRIMARY KEY (...)` clause.
- MinIO `secret_key` is `SecretStr` with a serializer revealing it only when persisting.
  Presigned URLs live ≤15 min (shorter of that and the store's expiry); they point at
  `minio:9000` — use `curl --resolve minio:9000:127.0.0.1` or the console's `/blob` proxy.
- **Frontend:** `lib/authz.ts` must be kept rung-for-rung with `authz.rego`. Tabs are buffers;
  clicking re-points the current tab; new tabs only on request; deleting sweeps all buffers;
  one keydown dispatcher, one command registry. Table shape is read with `SELECT * ... LIMIT 0`.
  HTML blobs shown as source only. `--vg-fg-muted` overridden in `app.css` for contrast.
- **Exploration gotchas:** globbing `backend/` without a subpath is dominated by `.venv` (4.7k
  files) — glob `backend/src/**/*.py`, `backend/tests/*.py` instead. Stale `.pyc` files may exist
  in `__pycache__` for tests that no longer exist.
