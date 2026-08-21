# DataPlatform — monorepo (`app/backend` FastAPI API + `app/frontend` React console)

## Commit

- Repository root: `/Users/norel/dataplatform` (single git repo; the code lives under `app/`).
- Branch at time of writing: **`blob-viewers`** (main branch is `main`).
- HEAD commit: **`539fdb9`** — "Draw pdfs the store mislabels, instead of downloading them".
  - `7386e5d` — "Add the console, with a viewer per blob format" (introduced `src/viewers/` and `src/lib/text.ts`; removed `medium()` from `lib/format.ts`).
  - `ec9adb9` — "add frontend init" (what the **previous** report described).
  - `8485acc` — "backend init".
- Working tree at time of writing carries uncommitted work on top of `539fdb9`, all on the **backend** side and unchanged since the last report:
  - modified: `app/backend/README.md`, `app/backend/docker-compose.yaml`, `app/backend/agent-knowledge/…`
  - untracked/new: `app/backend/Dockerfile`, `app/backend/.dockerignore`, `app/backend/config.docker.yaml`, `app/backend/scripts/`, and both `agent-knowledge/` trees.
- **Backend was verified unchanged** in structure since `ec9adb9` (same 60 Python files, same 6 migrations, same feature packages). The two new commits are frontend-only.

## Description

Two applications that make one product:

1. **`app/backend` — DataPlatform API.** Python 3.14 + FastAPI. Abstracts management of data held across several underlying stores. Authentication is by **API keys the platform issues itself** (`dpk_…`, stored only as a SHA-256 digest). Authorization is delegated wholesale to an external **Open Policy Agent** Rego policy — the API builds a question and OPA answers it, failing **closed** (503) when OPA is unreachable. The schema is owned by **Alembic** revisions applied automatically at startup. ~60 Python files (`src/` 45, `tests/` 20, 6 migrations, `main.py`), 2 Rego files.
2. **`app/frontend` — dataplatform console.** React 19 + TypeScript + Vite SPA (`"name": "dataplatform-console"`). A keyboard-first, vim/Neovim-flavoured UI over the API: blobs (upload, and **view** — image, video, audio, pdf, html/markdown/text), tables (create, add columns, insert rows, run SQL), workspaces (projects). **32 source files** under `src/`: 6 `lib` modules, 11 components, **10 viewers**, `App.tsx`, `main.tsx`, 3 CSS layers. Only runtime deps are `react` and `react-dom`; no router, no state library, no CSS framework, no pdf.js.

Core ideas of the platform (shared vocabulary between both sides):

- **Two scopes.** `system` — **datastores** and **users**; only platform administrators may act on them. `project` — **projects** and the **tables** and **blobs** under them; governed by the caller's `ProjectRole` (`viewer < editor < admin < owner`).
- **The API never decides permissions itself.** It builds `AuthorizationRequest` documents (with a computed `scope`) and asks OPA. List endpoints filter through one `allowed_resource_ids` call rather than re-implementing the rules in Python.
- **Limits are enforced by the engine, not by parsing text.** SQL privilege is chosen from the policy's answer and then enforced by SQLite's authorization callback. Blob permission is the **signature** on a presigned URL (method + bucket + key), enforced by MinIO.
- **The platform never carries blob bytes.** Creating a blob returns a record plus a presigned `PUT` URL; the client sends the bytes directly.
- **The console's two loud ideas:** (1) no form changes a table without first printing the SQL statement it composed, because the platform does not read the statement either; (2) **what to do with a blob's bytes is one decision made in one place** — `viewers/registry.ts` — so adding a format is adding a file and a line.

Entrypoints: backend `uv run fastapi dev main.py` (or `docker compose up -d`); frontend `npm run dev` → `http://localhost:5173`.

## File Structure

| Path | Description | Usage frequency |
|---|---|---|
| `/Users/norel/dataplatform/` | Repo root: `.gitignore`, `.claude/settings.local.json`, `chart/`, `app/`. | rare |
| `/Users/norel/dataplatform/chart/` | Helm chart `dataplatform`; its only dependency is the Apache **Ozone** chart 0.2.0 (`charts/ozone-0.2.0.tgz`, `Chart.lock`, `values.yaml`, `templates/_helpers.tpl`). Not wired to the API. | rare |
| `/Users/norel/dataplatform/app/backend/` | The API project (uv/pyproject managed). | constant |
| `app/backend/main.py` | Entry point: loads config via `src.platform.environment`, builds the app, exposes module-level `app`; exits 1 on `ConfigurationError`. | on start |
| `app/backend/README.md` | Access model, catalogue, visibility, tables & privileges, blobs & signed URLs, Docker, keys, migrations, tests, layout. **The best single document on the backend.** | reference |
| `app/backend/Dockerfile`, `.dockerignore` | Image for the API; source is bind-mounted over it read-only in compose so edits reload. | dev |
| `app/backend/docker-compose.yaml` | `api` + `opa` (1.19.0) + `minio` (+ console on 9001) + a one-shot `seed` container. Named volumes `api-data`, `minio-data`. Ports overridable via `API_PORT`/`OPA_PORT`/`MINIO_PORT`. | dev |
| `app/backend/config.docker.yaml` | Committed config for compose; bootstrap key `dpk_local_docker_compose_development_key`, DB `sqlite:////data/metadata/platform.db`, OPA at `http://opa:8181`. Nothing in it is secret by design. | dev |
| `app/backend/config.example.yaml`, `config.yaml` | Template and local (gitignored) configuration. | setup |
| `app/backend/scripts/seed-datastores.sh` | The "administrator" that registers `sqlite-main`, `sqlite-scratch`, `minio-blobs` through the API. Idempotent. | dev |
| `app/backend/alembic.ini` | Alembic settings. Deliberately no `sqlalchemy.url` — it comes from `config.yaml` via `migrations/env.py`. | migrations |
| `app/backend/migrations/versions/` | `0001_baseline`, `0002_system_level_datastores`, `0003_project_tables`, `0004_api_keys`, `0005_project_blobs`, `0006_datastore_visibility`. Revisions never import from `src`. | history |
| `app/backend/policies/dataplatform/` | `authz.rego` and `authz_test.rego` (`opa test policies -v`). | every request |
| `app/backend/src/features/` | One package per thing the platform offers: `users/`, `projects/`, `tables/`, `blobs/`, `datastores/` — each with `model.py`, `service.py`, `router.py` (+ `storage.py` where a feature owns a storage protocol). | every request |
| `app/backend/src/features/datastores/implementations/` | `base.py`, `sqlite.py`, `minio.py`, `_sqlite_privileges.py`. One module per concrete store. | every request |
| `app/backend/src/identity/` | Who the caller is: `keys.py`, `model.py`, `service.py`, `caller.py`, `bootstrap.py`. | every request |
| `app/backend/src/authz/` | What the caller may do: `policy.py`, `opa.py`, `enforcement.py`. | every request |
| `app/backend/src/database/` | `engine.py`, `migrations.py`. Knows nothing about features. | on start |
| `app/backend/src/platform/` | Plumbing: `config.py`, `environment.py`, `exceptions.py`, `error_handlers.py`, `state.py`, `dependencies.py`. Knows nothing about features. | every request |
| `app/backend/tests/` | 20 pytest files, `asyncio_mode = auto`. `conftest.py` boots a real `opa` binary and (for blobs) two real MinIO servers, builds the DB **through the migrations**, and writes users + keys straight into the database. Nothing in the request path is stubbed. | CI/dev |
| `/Users/norel/dataplatform/app/frontend/` | The console (npm/Vite managed). | constant |
| `app/frontend/index.html`, `vite.config.ts`, `tsconfig.json`, `package.json` | Vite shell, the two dev proxies, strict TS config, scripts `dev`/`build`/`preview`. | dev |
| `app/frontend/README.md` | Why the two proxies exist, what the console assumes about the API, the keyboard table, buffers/workspaces, **the viewers section (new)**, the transport, the blob tree, layout. | reference |
| `app/frontend/src/lib/` | `api.ts` (whole API surface + signed-URL rewrite), `sql.ts` (statement building), `media.ts` (signed download URL cache), `format.ts` (bytes/latency/timestamps/**timecode**), `tree.ts` (blob keys read as a hierarchy), **`text.ts` (bytes read as text, with the 1 MB ceiling — new)**. | every render |
| `app/frontend/src/viewers/` | **New.** The format abstraction: `viewer.ts` (the interface + matchers), `registry.ts` (the only list), `Frame.tsx` (stage + caption + `Undecodable`), `Transport.tsx` (`useTransport` + `Transport`), `Image.tsx`, `Video.tsx`, `Audio.tsx`, `Pdf.tsx`, `Source.tsx` (html/markdown/text), `Unknown.tsx` (fallback). | every blob render |
| `app/frontend/src/components/` | `Shell.tsx` (Tabline/Cmdline/WorkspaceSegment/Statusline/Canvas), `Rail.tsx`, `WorkspacePane.tsx`, `TablePane.tsx`, `BlobPane.tsx`, `ContactSheet.tsx`, `dialogs.tsx`, `Overlay.tsx`, `Palette.tsx`, `Gate.tsx`, `bits.tsx`. | every render |
| `app/frontend/src/vigil/` | The **Vigil** design system, vendored unmodified (`tokens.css`, `components.css`) plus the console's own layer `app.css` (everything prefixed `dp-`, resolves tokens only; ~620 lines, now with media/transport/player/deck/source sections). | every render |
| `app/frontend/design/` | Design handoff: `VIGIL-DESIGN-SYSTEM.md`, `gallery.html`, `css/tokens.css`, `css/components.css`, `assets/` (`vigil-mark.svg`, `icon-reference/stroke-0{1..6}.svg`). **Gitignored** (`design/` in `.gitignore`), so local-only reference material. | reference |
| `app/frontend/public/` | `mark.svg`, `favicon.svg`. | rare |
| `app/frontend/node_modules/` | ~2.5k files. Ignore when exploring. | never |
| `app/backend/agent-knowledge/`, `app/frontend/agent-knowledge/` | Agent knowledge (untracked). **The frontend copy is the canonical one.** | rare |

## Objects

### Frontend — `src/viewers/viewer.ts` (the abstraction)
- `interface ViewerProps { url: string; stored: StoredBlob; blob: Blob }` — `url` is signed, proxied, good for one read for a few minutes; `stored` is never null (a viewer is only asked to show bytes that exist).
- `interface ThumbProps extends ViewerProps { onBroken: () => void }` — a thumbnail must be able to say it could not draw.
- `interface Viewer { kind: string; types: readonly string[]; extensions: readonly string[]; render: ComponentType<ViewerProps>; thumb?: ComponentType<ThumbProps> }`. A `types` entry ending in `/` matches a whole family (`image/` claims `image/avif`). `kind` is the viewer's own lowercase name for itself, printed in captions and the contact sheet.
- Nothing in `viewer.ts` imports a viewer; viewers import it, the registry imports both, panes import only the registry.

### Frontend — the viewers (each exports one `Viewer` const)
| Const | Path | kind | types | extensions | thumb? |
|---|---|---|---|---|---|
| `image` | `src/viewers/Image.tsx` | `image` | `image/` | png jpg jpeg gif webp avif svg bmp ico tif tiff | yes (`<img>`) |
| `video` | `src/viewers/Video.tsx` | `video` | `video/` | mp4 mov m4v webm ogv avi mkv | yes (muted `<video>` first frame) |
| `audio` | `src/viewers/Audio.tsx` | `audio` | `audio/` | mp3 wav ogg oga flac m4a aac opus weba | no |
| `pdf` | `src/viewers/Pdf.tsx` | `pdf` | `application/pdf` | pdf | no |
| `html` | `src/viewers/Source.tsx` | `html` | `text/html`, `application/xhtml+xml` | html htm xhtml | no |
| `markdown` | `src/viewers/Source.tsx` | `markdown` | `text/markdown`, `text/x-markdown` | md markdown mdown | no |
| `text` | `src/viewers/Source.tsx` | `text` | `text/`, `application/json`, `application/xml`, `application/x-yaml`, `application/yaml` | txt text log json csv tsv xml yaml yml toml ini sql | no |
| `unknown` | `src/viewers/Unknown.tsx` | `file` | *(none)* | *(none)* | no — fallback only |

- `src/viewers/Pdf.tsx`: `INLINE_LIMIT = 32 * 1024 * 1024`, `SERVED_AS_PDF = "application/pdf"`, inner `useRenderable`, component `Document`.
- `src/viewers/Source.tsx`: inner `Printed` component, factory `printing(kind, types, extensions, note?)`.
- `src/viewers/Video.tsx`: inner `Screen` component (fullscreen via `document.fullscreenElement`); `src/viewers/Audio.tsx`: inner `Deck`.
- `src/viewers/Transport.tsx`: `interface Playback { ready, playing, current, duration, buffered, muted, failed }`, `const IDLE: Playback`.

### Frontend — `src/lib/text.ts`
- `TEXT_LIMIT = 1024 * 1024`, `class TooLarge extends Error { size }`, `interface Source { text; lossy; lines }`.

### Frontend — `src/lib/api.ts`
- Types: `Uuid`, `ProjectRole` (`viewer|editor|admin|owner`), `DataType` (`table|blob`), `CurrentUser`, `Project`, `Membership`, `CatalogueEntry`, `Table`, `ColumnDefinition`, `QueryResponse`, `Blob`, `StoredBlob`, `BlobView`, `PresignedAccess`, `CreatedBlob`.
- `class ApiError extends Error` — carries `status` and the platform's own sentence. `status === 0` means the API did not answer.
- `const api = { … }` — the whole HTTP surface (see Functions). Module-level mutable `key` set by `setKey`, sent as `Authorization: Bearer` on every call.

### Frontend — `src/lib/tree.ts`
- `Branch<T>`, `Leaf<T>`, `Node<T> = Branch|Leaf`, internal `Draft<T>`, `Run { text, hit }`.

### Frontend — `src/App.tsx`
- `Selection` (`workspace` | `table{name}` | `blob{key}`), `Buffer` (`id`, `workspaceId`, `selection`), `WorkspaceData` (`tables`, `blobViews`, `members`, `loading`), `EMPTY`, `Confirm`, `Overlay` union (`palette | new-workspace | new-table | upload | grant | confirm`). `KEY_STORE = "dataplatform.key"` in `localStorage`; module-level `bufferSeed`/`nextBufferId`.

### Frontend — components
- `Tab`, `Mode` (`normal|command|busy`), `SIGIL` map (`workspace ◫`, `table ▦`, `blob ◈`) — `components/Shell.tsx`.
- `RailRow` union (`overview | table | branch | leaf`) — `components/Rail.tsx`.
- `PaletteItem` — `components/Palette.tsx`.
- `TableActions` (`addColumn`, `insertRow`) — `components/TablePane.tsx`.
- `DraftColumn`, `StepState` (`pending|running|done|failed`), module-level `seed`/`nextId` — `components/dialogs.tsx`.
- `ROW_LIMIT = 200` — `lib/format.ts`. (**`Medium` and `medium()` were removed in `7386e5d`** — the registry replaced them.)

### Backend — configuration `src/platform/config.py`
- `MINIMUM_BOOTSTRAP_KEY_LENGTH = 32`; `DatabaseConfig`, `BootstrapAdminConfig`, `AuthConfig`, `OpaConfig`, `AppConfig`.

### Backend — persistence models
- `User` — `src/features/users/model.py` (id, email unique+indexed, name, is_platform_admin, creation_date).
- `ApiKey` — `src/identity/model.py` (id, user_id, name, secret_hash unique+indexed, creation/expiration/revocation dates).
- `ProjectRole(StrEnum)`, `Project`, `ProjectMember` — `src/features/projects/model.py`.
- `Table` (`__tablename__ = "projecttable"`) — `src/features/tables/model.py`.
- `Blob` — `src/features/blobs/model.py`.
- `DataStoreVisibility(StrEnum)`, `DataStoreImplementationColumn(TypeDecorator)`, `DataStore`, `PERSISTING = {"reveal_secrets": True}` — `src/features/datastores/model.py`.

### Backend — storage contracts
- `src/features/datastores/storage.py`: `DataType(StrEnum)`, `namespace_of(*, project_id)`, `DataStoreQuery`, `DataStoreQueryResponse`.
- `src/features/tables/storage.py`: `validate_identifier`, `_IDENTIFIER`, `_COLUMN_TYPE`, `QueryPrivilege(StrEnum)` (READ_ONLY/READ_WRITE), `ColumnDefinition`, `TableStorage` (runtime-checkable Protocol).
- `src/features/blobs/storage.py`: `validate_object_key`, `_KEY_SEGMENT`, `_MAX_KEY_LENGTH = 1024`, `BlobOperation(StrEnum)`, `BlobDescription`, `PresignedAccess`, `BlobStorage` Protocol.
- `src/features/datastores/implementations/base.py`: `DataStoreImplementationBase(BaseModel, ABC)`.
- `sqlite.py`: `SQLiteDataStore`. `minio.py`: `MinIODataStore` (endpoint, access_key, `secret_key: SecretStr`, secure, region, `presigned_url_expiry_seconds`), `_BUCKET_NAME`, `_ABSENT_CODES`, `_REDACTED = "**********"`.
- `_sqlite_privileges.py`: `type Authorizer`, `_SCHEMA_TABLE`, `_READ_ACTIONS`, `_WRITE_ACTIONS`, `_CATALOGUE_ACTIONS`, `_MECHANICS`. Default is DENY.

### Backend — authorization vocabulary `src/authz/policy.py`
- `ResourceScope(StrEnum)`: SYSTEM, PROJECT.
- `ResourceType(StrEnum)`: PROJECT, DATASTORE, TABLE, BLOB, USER; `.scope` reads `_SCOPES`; an import-time check raises `ConfigurationError` for any unscoped type.
- `Action(StrEnum)`: `project.read/update/delete/manage_members`, `datastore.create/read/query/update/delete`, `table.create/read/query/write/delete`, `blob.create/read/download/upload/delete`, `user.create/read/issue_key`.
- `Subject`, `Resource` (+ computed `scope`), `AuthorizationRequest`, `Decision`; Protocols `PolicyDecisionPoint`, `ResourceFilter`.

### Backend — runtime objects
- `OpaPolicyDecisionPoint` (`src/authz/opa.py`), `AccessEnforcer` (`src/authz/enforcement.py`), `ApplicationServices` frozen dataclass (`src/platform/state.py`), `IssuedApiKey` (`src/identity/service.py`), `DataStoreCatalogueEntry` (`src/features/datastores/catalogue.py`).
- Exceptions (`src/platform/exceptions.py`): `DataPlatformError` → `ConfigurationError`, `SchemaMigrationError`, `ObjectNotFoundError`, `DuplicateObjectError`, `AuthenticationError`→`InvalidApiKeyError`, `AuthorizationError`→`PolicyDecisionPointError`/`PermissionDeniedError`, `StorageError`→`UnsuitableDataStoreError`/`TableProvisioningError`/`BlobProvisioningError`/`QueryRefusedError`/`QueryFailedError`.
- Request/response models: users `CurrentUserResponse`/`UserResponse`/`CreateUserRequest`/`CreateApiKeyRequest`/`ApiKeyResponse`/`IssuedApiKeyResponse`/`CreatedUserResponse`; projects `CreateProjectRequest`/`GrantMembershipRequest`/`ProjectMembershipResponse`; tables `CreateTableRequest`/`TableQueryRequest`; blobs `CreateBlobRequest`/`BlobView`/`CreatedBlob`/`BlobAccessRequest` + `_ACCESS_LIFETIME = timedelta(minutes=15)`; datastores `CreateDataStoreRequest`/`UpdateDataStoreVisibilityRequest`.

## Functions

### Frontend

| Function / component | Path |
|---|---|
| `claimsType(viewer, contentType)`, `claimsName(viewer, key)` | `src/viewers/viewer.ts` |
| `resolve(contentType, key) → Viewer` — the single format decision; module-level `viewers` array, order is load-bearing | `src/viewers/registry.ts` |
| `Frame({kind, stored, bare, children})`, `Undecodable({stored})` | `src/viewers/Frame.tsx` |
| `useTransport(ref)` (inner `read`, `fail`, `toggle`, `seek`, `mute`), `Transport({playback, label, children})` | `src/viewers/Transport.tsx` |
| `Screen` (+ `video` const) | `src/viewers/Video.tsx` |
| `Deck` (+ `audio` const) | `src/viewers/Audio.tsx` |
| `useRenderable(props)`, `Document` (+ `pdf` const) | `src/viewers/Pdf.tsx` |
| `Printed`, `printing(...)` (+ `html`/`markdown`/`text` consts) | `src/viewers/Source.tsx` |
| `readSource(url, size, signal)` (+ `TEXT_LIMIT`, `TooLarge`) | `src/lib/text.ts` |
| `setKey`, `call<T>`, `readDetail`, `keyPath`, `viaProxy(signed)`, `uploadTo(access, file)` | `src/lib/api.ts` |
| `api.me`, `.listProjects`, `.createProject`, `.listMembers`, `.grantMembership`, `.catalogue`, `.listTables`, `.createTable`, `.deleteTable`, `.query`, `.listBlobs`, `.readBlob`, `.createBlob`, `.deleteBlob`, `.blobAccess` | `src/lib/api.ts` |
| `isIdentifier`, `literal`, `insertStatement`, `addColumnStatement`, `selectStatement`, `createTableSketch`, `verbOf`, `isRead` | `src/lib/sql.ts` |
| `build`, `flatten`, `keptUnder`, `branchPaths`, `ancestors`, `runs` | `src/lib/tree.ts` |
| `downloadUrl(project, key)`, `forget(project, key)`; `MARGIN_MS = 60_000` | `src/lib/media.ts` |
| `bytes`, `latency`, `stamp`, `clock`, **`timecode`** | `src/lib/format.ts` |
| `App()` — holds all state; inner `say`, `report`, `signIn`, `signOut`, `loadWorkspace`, `loadPlatform`, `sameBuffer`, `openBuffer`, `closeBuffer`, `switchWorkspace`, `openRow`, `runTyped`, the single `keydown` dispatcher, and the `commands` registry | `src/App.tsx` |
| `Tabline`, `Cmdline`, `WorkspaceSegment`, `Statusline`, `Canvas` | `src/components/Shell.tsx` |
| `railRows(tables, visible)`, `Name`, `Rail` | `src/components/Rail.tsx` |
| `WorkspacePane` | `src/components/WorkspacePane.tsx` |
| `TablePane` (inner `run`, `reload`) | `src/components/TablePane.tsx` |
| `BlobPane` (inner `replace`; calls `resolve(...)` then renders `viewer.render`) | `src/components/BlobPane.tsx` |
| `ContactSheet`, `Shot` (uses `viewer.thumb`, falls back to `viewer.kind` text) | `src/components/ContactSheet.tsx` |
| `useSubmit`, `NewWorkspaceDialog`, `GrantDialog`, `NewTableDialog`, `AddColumnDialog`, `InsertRowDialog`, `UploadDialog`, `ConfirmDialog` | `src/components/dialogs.tsx` |
| `useOverlay`, `Dialog`, `Modal` | `src/components/Overlay.tsx` |
| `Palette`, `Row` | `src/components/Palette.tsx` |
| `Gate` | `src/components/Gate.tsx` |
| `Head`, `Empty`, `Loading`, `Problem`, `Field`, `Sketch`, `KV`, `Fact` | `src/components/bits.tsx` |
| root render into `#root` (StrictMode; imports the three CSS layers in order) | `src/main.tsx` |

### Backend

| Function | Path |
|---|---|
| `main()`, module-level `app` | `main.py` |
| `create_app(*, config)`, inner `lifespan`, `GET /` handler `default()` | `src/app.py` |
| `load_config(*, path)` | `src/platform/config.py` |
| `configuration_path()`, `load_configuration()`; `CONFIG_PATH_VARIABLE = "DATAPLATFORM_CONFIG"` | `src/platform/environment.py` |
| `create_database_engine`, `open_session` | `src/database/engine.py` |
| `upgrade_to_head`, `_alembic_configuration`, `_predates_alembic`; `BASELINE_REVISION`, `_BASELINE_TABLES` | `src/database/migrations.py` |
| `get_services`, `get_session`, `get_enforcer`, `get_configuration` (+ `Services`/`DatabaseSession`/`Enforcer`/`Configuration` aliases) | `src/platform/dependencies.py` |
| `register_error_handlers(*, app)` | `src/platform/error_handlers.py` |
| `generate_key()`, `digest_of(*, key)`; `KEY_PREFIX = "dpk_"`, `_SECRET_BYTES = 32` | `src/identity/keys.py` |
| `current_user`, `current_subject` | `src/identity/caller.py` |
| `issue_api_key`, `authenticate`, `_is_usable`, `list_api_keys`, `revoke_api_key` | `src/identity/service.py` |
| `ensure_bootstrap_admins`, `_ensure_administrator`, `_ensure_key`, `_ensure_key_is_still_theirs`; `BOOTSTRAP_KEY_NAME` | `src/identity/bootstrap.py` |
| `OpaPolicyDecisionPoint.decide/filter_allowed/_query/check_reachable` | `src/authz/opa.py` |
| `AccessEnforcer.ensure_allowed/is_allowed/keep_allowed` | `src/authz/enforcement.py` |
| `create_user`, `get_user`, `find_user_by_email`, `list_users`, `describe_subject` | `src/features/users/service.py` |
| `create_project`, `get_project`, `list_projects`, `roles_of_user`, `set_member_role`, `list_members` | `src/features/projects/service.py` |
| `_storage_behind`, `get_table`, `list_tables`, `create_table`, `delete_table`, `run_query` | `src/features/tables/service.py` |
| `_storage_behind`, `get_blob`, `list_blobs`, `create_blob`, `describe_blob`, `grant_access`, `delete_blob` | `src/features/blobs/service.py` |
| `create_datastore`, `get_datastore`, `list_datastores`, `set_visibility`, `delete_datastore`, `run_query` | `src/features/datastores/service.py` |
| `_describe`, `list_catalogue` | `src/features/datastores/catalogue.py` |
| `build_authorizer` (inner `authorize`), `is_refusal` | `src/features/datastores/implementations/_sqlite_privileges.py` |
| `_unreachable`, `MinIODataStore.*` (bucket provisioning, presigning, describe, delete) | `src/features/datastores/implementations/minio.py` |
| `namespace_of(*, project_id)` → `p<uuid.hex>` | `src/features/datastores/storage.py` |
| `create_users_router`, `create_projects_router`, `create_tables_router`, `create_blobs_router`, `create_datastores_router` (each with a local `_as_resource` helper) | `src/features/*/router.py` |

### HTTP surface (what the console consumes)

- `GET /` (health, no credentials).
- Users: `GET /users/me`, `POST|GET /users/me/api-keys`, `DELETE /users/me/api-keys/{key_id}`, `POST /users/`, `GET /users/`, `POST /users/{user_id}/api-keys`.
- Projects: `POST /projects/`, `GET /projects/`, `GET /projects/{id}`, `GET /projects/{id}/members`, `PUT /projects/{id}/members`.
- Tables (`/projects/{project_id}/tables`): `POST /`, `GET /`, `GET /{table_name}`, `POST /{table_name}/query`, `DELETE /{table_name}`.
- Blobs (`/projects/{project_id}/blobs`): `POST /`, `GET /?prefix=`, `GET /{key:path}`, `POST /{key:path}/access`, `DELETE /{key:path}`.
- Datastores: `GET /datastores/query`, `GET /datastores/catalogue`, `POST /datastores/`, `GET /datastores/`, `GET /datastores/{name}`, `PATCH /datastores/{name}` (visibility), `DELETE /datastores/{name}`.

## Dependencies

### Frontend (`app/frontend/package.json`)
- Runtime: **react** ^19.1, **react-dom** ^19.1. Nothing else — no router, no query library, no CSS framework, **no pdf.js** (the browser's own pdf reader is used through an `<iframe>`).
- Dev: **vite** ^7, **@vitejs/plugin-react** ^5, **typescript** ^5.7, `@types/node` ^26.2, `@types/react`, `@types/react-dom`.
- Build: `tsc -b && vite build`. TS is `strict` with `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`, `verbatimModuleSyntax`, `isolatedModules`, `noEmit`; target/lib ES2022 + DOM.
- Browser APIs leaned on: `fetch` + `AbortController`, `TextDecoder` (including `{fatal: true}` for the lossy-UTF-8 check), `URL.createObjectURL`/`revokeObjectURL`, `HTMLMediaElement` events + `buffered` TimeRanges, the Fullscreen API, `localStorage`.
- Runtime services it needs: the **API on :8000** and **MinIO on :9000**, both reached through the Vite dev proxies (`/api` and `/blob`).

### Backend (`app/backend/pyproject.toml`, Python ≥3.14, uv)
- **alembic** ≥1.19.1, **fastapi** ≥0.136.3, **pydantic** ≥2.13.4, **sqlmodel** ≥0.0.38 (+SQLAlchemy), **httpx** ≥0.28.1, **loguru** ≥0.7.3, **pyyaml** ≥6.0.3, **email-validator** ≥2.3.0, **minio** ≥7.2.20, **urllib3** ≥2.7.0 (named explicitly so the MinIO datastore's direct import survives minio changing its HTTP client).
- stdlib `sqlite3` (including the authorizer API), `secrets`, `hashlib`.
- Dev group: `fastapi[standard]`, `pytest` ≥9.1.1, `pytest-asyncio` ≥1.4 (auto mode), `pytest-cov` ≥7.1 (`fail_under = 80`), `ruff` ≥0.16.3 (`select = E,F,W,I,UP,B,SIM,RET,C4,S`, line-length 96), `ty` ≥0.0.39.

### External services / tooling
- **Open Policy Agent** (`openpolicyagent/opa:1.19.0`, or a local `opa` binary) serving `dataplatform/authz/decision` and `dataplatform/authz/allowed_resource_ids`. Required at runtime — without it everything guarded is a 503.
- **MinIO** (`quay.io/minio/minio:latest`), API on 9000, console on 9001. Needed for blobs; the blob tests run **two** independent servers.
- **Database**: any SQLAlchemy URL; SQLite by default.
- **Docker Compose** for the whole stack; **curl** image for the seeding container.
- **Helm/Kubernetes**: `chart/` depends on the Apache Ozone chart.
- No external identity provider — the platform issues its own credentials.

## Notable design notes / gotchas

### Frontend — viewers (the newest and most important subsystem)
- **One list, one decision.** `resolve(contentType, key)` in `registry.ts` is the whole of the console's knowledge about formats. Panes (`BlobPane`, `ContactSheet`) call it and render `viewer.render` / `viewer.thumb`; they contain no format conditionals.
- **Order in `viewers` is load-bearing in one direction:** a viewer claiming an exact type must precede one claiming its family, or `text/` would swallow `text/html`. Current order: `image, video, audio, pdf, html, markdown, text`.
- **Type first, name second, never mixed.** `claimsType` is tried across *all* viewers before `claimsName` is tried across any. The stored type is what the browser will act on; the key is a guess, worth making only because `application/octet-stream` is what most uploads are labelled.
- `claimsName` refuses a dot that lives in a directory segment: `v1.2/notes` has no extension.
- `unknown` claims **no** type and no extension — it is the `??` fallback, so it can never steal a format a real viewer would take.
- **The pdf viewer is where the registry's vote and the browser's vote diverge** (commit `539fdb9`). The registry may pick pdf from the *key*, but a browser routes on `Content-Type` alone, so an octet-stream-labelled pdf would be **downloaded** rather than drawn. `useRenderable`: if the header already says `application/pdf`, point the iframe at the signed URL; otherwise fetch once, check the leading `%PDF-` bytes, and hand back a `URL.createObjectURL(new window.Blob([...], {type: "application/pdf"}))`. The signature check is why the name is never taken as evidence — and why the iframe needs no `sandbox`. Above `INLINE_LIMIT` (32 MB) it refuses and offers "open bytes". Note `window.Blob` is used explicitly because `Blob` in this codebase usually means the API record.
- `useRenderable` **resets its state unconditionally at the top of the effect**, because the component is reused as the reader moves between blobs and a stale verdict would outlive its blob.
- **HTML is shown as source and never rendered** — a blob is a stranger's bytes and the page holds an API key.
- `Source` is the only viewer that must hold the whole blob, hence the only one with a ceiling (`TEXT_LIMIT` = 1 MB). `readSource` **decodes twice**: a strict `TextDecoder("utf-8", {fatal:true})` to learn whether it was text at all, then a lenient one to have something to show; `lossy` is surfaced to the reader rather than silently printing `�`.
- **The transport is built, not borrowed.** `controls` draws browser chrome that matches nothing in the design system. The seek bar stays an `<input type="range">` under the paint so arrows/Home/End/screen-reader slider semantics survive. Its track is three layers (played / fetched-but-unplayed / not here) via CSS custom properties `--done` and `--ahead` — the middle layer is the only place the console says whether a stall is the network or the file.
- `useTransport` is keyed on the **ref alone**; `duration` of `Infinity`/`NaN` is carried through as-is so the bar disables itself rather than lying. `play()` rejection (autoplay policy or decode failure) sets `failed` rather than throwing.
- `Undecodable` exists for the common QuickTime case: a `.mov` carrying H.265 is a valid file Safari plays and Chrome will not — reported as a browser limit, not as damage.
- `viewer.kind` is what the blob pane's meta line and the contact sheet caption print, so the name is never kept in step by hand.
- Formats with no `thumb` get their `kind` printed in the frame; `stored === null` gets a **dashed** frame (`is-hollow`); a thumbnail that fires `onError` gets "preview refused". Solid means empty, dashed means deliberately not there.

### Frontend — the rest
- **Two dev proxies, and both are deliberate** (`vite.config.ts`). `/api` → `127.0.0.1:8000` because the API sets **no CORS headers**. `/blob` → `127.0.0.1:9000` with `headers: { Host: "minio:9000" }` set **on the proxy options, not in a `proxyReq` handler** — a request carrying `Expect: 100-continue` has already flushed its headers by the time that event fires, which would break uploads over roughly a megabyte and nothing smaller. `changeOrigin` is `true` for `/api` and **`false`** for `/blob`. For a real deployment neither proxy is the answer.
- `viaProxy()` keeps path and query byte-for-byte, because they carry the AWS signature.
- **A tab is a buffer** — one open object (table, blob, or workspace overview). The workspace is a property of the *buffer*, not the window, so two tabs can sit in two different workspaces; that is why the workspace picker lives in the statusline. New buffers open **beside** the current one, not at the end. Workspace data is cached per workspace in `data: Record<Uuid, WorkspaceData>`.
- **One keyboard dispatcher** (a single `window` `keydown` listener in `App.tsx`) and **one command registry** shared by the `:` command line and the ⌘K palette, so they cannot disagree. Keys: `1`–`9` buffers, `j`/`k` rail, `↵` open/fold, `:` command line, `/` or `f` find, `⌘K` palette, `⌘↵` run statement, `esc` dismiss. Commands: `:new workspace`, `:new table`, `:upload`, `:add column`, `:insert row`, `:find`, `:close`, `:grant access`, `:reload`, `:density`, `:gloss`, `:forget key`.
- The command line also accepts a bare **number** to jump to that buffer, then exact-match, then prefix-match, then object-name match.
- **A table's shape is read with `SELECT * FROM <table> LIMIT 0`** and taken from `metadata.columns` — `PRAGMA` is refused by the privilege the query endpoint connects with, and that is correct.
- `TablePane.run(text, {quiet})` — a statement run from a dialog reports its refusal inside that dialog, so `quiet` keeps the message off the panel the reader cannot see.
- **`stored: null` is a normal state** (recorded, never filled) and is rendered as a dashed frame / plain sentence, never a broken image.
- Membership is loaded in a *separate* try/catch, because a viewer may be refused `GET /members` and that must not empty the rest of the workspace.
- `openBuffer` computes everything **outside** the state updater on purpose: an updater that mints an id and sets other state is not pure, and React may run it twice (StrictMode does).
- Blob keys are single strings; the rail *infers* a tree from the slashes. Branches disappear with their last leaf. Search matches the **whole key** (slashes included), highlights per-segment runs (`runs()` clips hits to the segment window), ignores folding, and the heading reports `[shown of total]`.
- The API key is kept in `localStorage` under `dataplatform.key`; `:forget key` clears it. `ApiError` with `status === 0` flips the statusline to "api unreachable".
- Signed download URLs are cached per `project/key` in `lib/media.ts` and re-minted 60 s before they lapse; `forget()` is called after a replace or delete.
- **Known deviation from the design handoff:** `--vg-fg-muted` is overridden in `src/vigil/app.css` from `#5A5852` to `#7C7A74` for contrast (≈2.8:1 → 4.5:1), which §13 of `VIGIL-DESIGN-SYSTEM.md` invites.
- `design/` is **gitignored**, so the vendored copies in `src/vigil/` are the ones that ship. New CSS in `app.css` for this subsystem: `.dp-media`, `.dp-media-stage(.is-bare)`, `.dp-page`, `.dp-transport*`, `.dp-player(:fullscreen)`, `.dp-deck*`, `.dp-source*`, `.dp-sheet`, `.dp-shot*`. Design-system classes it leans on: `.vg-caption`, `.vg-withheld`, `.vg-steps`.

### Backend
- `src/app.py` is the only module naming OPA; everything else depends on `PolicyDecisionPoint`/`ResourceFilter`. Authentication has no such seam by design.
- **Layout rule 1:** a feature owns its storage protocol (`TableStorage` with tables, `BlobStorage` with blobs), which lets a blob store decline to have table methods. **Rule 2:** no `__init__.py` re-exports anything, so the import graph stays acyclic. **Rule 3:** `platform` and `database` know nothing about features. `identity` imports `features.users` and `authz` imports `features.projects.model` — the only two crossings, and both are the domain being honest.
- `Resource.scope` is computed from the type, never supplied.
- `POST /projects/` performs **no** enforcer call: any authenticated user may create a project and becomes its `owner`.
- The three `/users/me/...` key endpoints are deliberately **not** put to the policy.
- Datastore and user endpoints ask the policy **before** the database, so a refusal cannot reveal whether a name exists. Project/table/blob endpoints fetch first, so a missing object is a 404.
- `GET /datastores/query` and `/datastores/catalogue` are declared before `/{datastore_name}`, so the literal paths win.
- **`GET /datastores/catalogue`** is the deliberate exception to the system scope: any authenticated caller may learn names/data types/descriptions (built field by field into `DataStoreCatalogueEntry`, so a new credential field cannot leak). Knowing a name opens nothing.
- **`visibility`** (`public`/`private`, default `public`) decides only whether a datastore appears in the catalogue. It is **hidden, not protected** — the policy never consults it.
- The table query endpoint is the only place `AccessEnforcer.is_allowed` is used: `table.write` is asked first and, if refused, `table.query` is *enforced*; the answer picks the `QueryPrivilege`. A decision-point failure raises rather than downgrading.
- SQLite: a namespace is a sibling database file (`warehouse__p<hex>.db`). A read-write caller **can** read `sqlite_master` within their own namespace, because `ALTER TABLE` requires it; documented, not a choice.
- MinIO: `secret_key` is a `SecretStr` **and** has a field serializer that reveals it for exactly one destination (the dump in `features/datastores/model.py` that writes the row). Every other dump, API responses included, gets `**********`.
- Blob keys are unique **per project**, not per datastore; a blob does not move between datastores. Wrong-type datastore → 400, unknown name → 404, unreachable store → **502**.
- Signed URLs cannot be withdrawn, so they are minted for 15 minutes (`_ACCESS_LIFETIME`), and the shorter of that and the datastore's `presigned_url_expiry_seconds` wins. Deleting goes through the API, never through a signed URL.
- A presigned URL points at `minio:9000`; from the host, follow one with `curl --resolve minio:9000:127.0.0.1 "<url>"` (or, in the console, through the `/blob` proxy).
- Bootstrap: `ensure_bootstrap_admins` runs on every start; changing the configured key rotates it (old one revoked), while re-using a revoked or somebody else's key raises `ConfigurationError` and stops the process.
- Autogenerated revisions render the implementation column as `src.datastore.DataStoreImplementationColumn()` — replace with `sa.JSON()`; revisions must never import from `src`. `render_as_batch=True` is on for SQLite.
- Pre-Alembic databases are detected (any of `user/project/projectmember/datastore/catalog` with no `alembic_version`) and stamped `0001_baseline`.
- Port 8000 collision: a host `fastapi dev` beats the published container port on localhost; use `API_PORT=8001 docker compose up -d`.
- The compose metadata database lives in the `api-data` volume, **not** in `mydb.db` beside the README — deliberately not the same database.
