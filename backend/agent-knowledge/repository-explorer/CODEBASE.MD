# DataPlatform — monorepo (`app/backend` FastAPI API + `app/frontend` React console)

> **This file is the canonical report.** A copy at
> `/Users/norel/dataplatform/app/frontend/agent-knowledge/repository-explorer/CODEBASE.MD`
> exists because the explorer has been run from both working directories; it is a
> pointer to this one.

## Commit

- Repository root: `/Users/norel/dataplatform` (single git repo; the code lives under `app/`).
- Branch: **`feature/table-primary-keys-ui`** (off `main` at `f3833a6`). Working tree carries
  only this report and its frontend pointer as uncommitted edits.
- HEAD commit: **`7e30d98`** — "State a key column's NOT NULL as a fact instead of a greyed-out toggle".
  - `eff821a` — "Let a table's primary key be asked for by marking its columns in the console"
  - `f3833a6` — "Let a table be created with a primary key by marking its columns" (backend)
  - `ee639a5` — "Move workspace membership out of the overview onto a members page of its own"
  - `69455d2` — "fix security issues + workspace admin management"
  - `bbf80d9` — "frontend changes"
  - `8f4094c` — "backend"
  - `1d3c9ac` — "Let owners remove people from a project, but never an owner"
  - `86127f2` — "Make owner a role only an owner may grant, and nobody inside may take back"
  - (earlier: `539fdb9`, `7386e5d`, `ec9adb9` "add frontend init", `8485acc` "backend init".)
- **What changed in `ee639a5` (frontend only; the backend, the Rego policy and the
  migrations are byte-for-byte what they were at `69455d2`):** membership stopped being a
  section of the workspace overview and became **a page of its own**.
  - New `Selection` variant `{ kind: "members" }` and a new component
    `src/components/MembersPane.tsx`.
  - `RailRow` gained `{ id: "members"; kind: "members" }`; `railRows()` now emits *two*
    "workspace pages" rows (`overview`, `members`) before tables and blobs, and `Rail.tsx`
    got a module-private `isPage(row)` so adding a third page touches only `railRows`.
  - `WorkspacePane` lost its Members list and gained `onOpenMembers`; the `members` tile in
    its fact band is now the way to the page.
  - `bits.tsx#Fact` gained optional `onOpen`/`title` — a fact that leads somewhere renders
    as a `<button class="vg-fact dp-fact-link">` instead of a `<div>`.
  - New command **`:members`** in `App.tsx`'s registry; the `members` tab kind in
    `Shell.tsx` (sigil `◌`) is finally minted, so the note in the previous report that it
    was dead is **no longer true**.
  - `rightsIn(me, project)` now takes a `Uuid | null` (the workspace id) rather than a
    `Project` object.
  - The frontend README grew a "The workspace's pages" section and the layout block now
    says `components/*Pane.tsx  workspace · members · table · blob`.
- **What changed in `f3833a6` (backend):** a table may now be created **with a primary key**,
  asked for by marking columns rather than as a field of its own.
  - `ColumnDefinition` gained `primary_key: bool = False`. Every column marked so forms **one**
    key together, in the order the columns were given — one mark is a single-column key,
    several are a composite one.
  - New module-level **`primary_key_of(columns) → tuple[str, ...]`** in
    `src/features/tables/storage.py`, exported in `__all__`. It reads the columns back as the
    single key they describe, and it is where the platform's own rule lives: **a key column may
    not be `nullable`**, and asking for both raises `ValueError` naming the columns. The rule is
    the platform's rather than an engine's because engines disagree — SQLite permits NULLs in a
    key column unless it is declared `NOT NULL` (documented legacy behaviour). Refusing the
    contradiction is what lets every implementation emit the `NOT NULL` that closes it.
  - `CreateTableRequest` gained a `@model_validator(mode="after") _check_primary_key` that just
    calls `primary_key_of`, so the contradiction comes back as a **422** rather than as a failed
    provisioning. The `TableStorage` protocol docstring now tells implementations to *ask*
    `primary_key_of` rather than work the key out themselves.
  - `SQLiteDataStore.create_table` appends `, PRIMARY KEY (a, b)` to the column definitions.
    **One form for both cardinalities**: a lone `INTEGER` column named in a table-level clause
    still becomes a rowid alias in SQLite, so there is no second case for single-column keys.
- **What changed in `eff821a` + `7e30d98` (frontend, this branch):** the console can now ask for
  the key that `f3833a6` accepts. **`NewTableDialog` is the only place it appears** — a key
  cannot be added by an `ALTER`, so `AddColumnDialog` has no such control.
  - `ColumnDefinition` in `src/lib/api.ts` gained `primary_key: boolean`, mirroring the backend
    field; `DraftColumn` inherits it, and `createTable` sends it.
  - Each column row gained a **`key` toggle**. The seeded first column (`id INTEGER`) is now
    marked by default, matching the backend README's canonical example.
  - `createTableSketch` renders the `PRIMARY KEY (…)` clause — in the **same single form the
    backend emits**, deliberately, so the printed sketch is not a shape the reader will not get.
  - **The key/nullable contradiction is made uncomposable rather than validated.** A local
    `mark(id, inKey)` helper sets `nullable: false` alongside `primary_key: true`, so no
    client-side copy of the backend's 422 rule exists to drift from it.
  - `7e30d98` fixed how that reads. The first attempt kept the nullable toggle in place but
    `disabled`, which collided two orthogonal signals on one element: `is-on` states a truth,
    `:disabled` states an affordance, and `.vg-btn:disabled { opacity: 0.4 }` drowned the
    highlight — a key column's `not null` rendered **weaker** than an ordinary one's, least
    certain exactly where it is most certain. While a column is in the key the toggle is now
    replaced by a non-interactive **`<span class="vg-tag dp-col-fact">not null</span>`**: the
    system already separates `.vg-btn` (a control) from `.vg-tag`/`.vg-label` (a stated fact),
    and a consequence of the mark would not answer a click. **`.dp-col-fact` overrides
    `.vg-tag`'s colour and padding at equal specificity, so it depends on `main.tsx` importing
    `app.css` after `components.css`** — do not reorder those imports.
  - `.dp-col-row`'s grid gained a cell and the nullable cell became `minmax(74px, auto)`, at
    both widths, so the toggle and the chip share a footprint and nothing shifts on toggle.

## Description

Two applications that make one product:

1. **`app/backend` — DataPlatform API.** Python 3.14 + FastAPI. Abstracts management of
   data held across several underlying stores. Authentication is by **API keys the platform
   issues itself** (`dpk_…`, stored only as a SHA-256 digest). Authorization is delegated
   wholesale to an external **Open Policy Agent** Rego policy — the API builds a question and
   OPA answers it, failing **closed** (503) when OPA is unreachable. The schema is owned by
   **Alembic** revisions applied automatically at startup. **52 Python modules** under `src/`
   + `main.py`, **19** pytest files (18 `test_*.py` + `conftest.py`), 6 migrations + `env.py`,
   2 Rego files.
2. **`app/frontend` — dataplatform console.** React 19 + TypeScript + Vite SPA
   (`"name": "dataplatform-console"`). A keyboard-first, vim/Neovim-flavoured UI over the API:
   blobs (upload, and **view** — image, video, audio, pdf, html/markdown/text), tables (create,
   add columns, insert rows, run SQL), workspaces (projects, and their membership on a page of
   its own). **34 source files** under `src/`: **7** `lib` modules, **12** components, 10
   viewers, `App.tsx`, `main.tsx`, 3 CSS layers. Only runtime deps are `react` and `react-dom`;
   no router, no state library, no CSS framework, no pdf.js.

Core ideas of the platform (shared vocabulary between both sides):

- **Two scopes.** `system` — **datastores** and **users**; only platform administrators may
  act on them. `project` — **projects** and the **tables** and **blobs** under them; governed
  by the caller's `ProjectRole` (`viewer < editor < admin < owner`).
- **The API never decides permissions itself.** It builds `AuthorizationRequest` documents
  (with a computed `scope`) and asks OPA. List endpoints filter through one
  `allowed_resource_ids` call rather than re-implementing the rules in Python.
- **Membership is two powers, not one.** `project.manage_members` shapes what people in a
  project may do; `project.remove_members` decides who is in it at all. Only an owner may grant
  `owner`; the `owner` role can never be taken back from inside the project (by demotion or
  removal, by a fellow owner or by the holder themselves). A platform administrator stands
  outside all of it.
- **Limits are enforced by the engine, not by parsing text.** SQL privilege is chosen from the
  policy's answer and then enforced by SQLite's authorization callback. Blob permission is the
  **signature** on a presigned URL (method + bucket + key), enforced by MinIO.
- **The platform never carries blob bytes.** Creating a blob returns a record plus a presigned
  `PUT` URL; the client sends the bytes directly.
- **The console's loud ideas:** (1) no form changes a table without first printing the SQL
  statement it composed, because the platform does not read the statement either; (2) what to
  do with a blob's bytes is one decision made in one place — `viewers/registry.ts`; (3) the
  console mirrors the policy in `lib/authz.ts` only to stop offering acts it knows will be
  refused — nothing there grants anything; (4) **a workspace's contents and a workspace's
  access are two pages, because they change for different reasons at different people's hands.**

Entrypoints: backend `uv run fastapi dev main.py` (or `docker compose up -d`);
frontend `npm run dev` → `http://localhost:5173`.

## File Structure

| Path | Description | Usage frequency |
|---|---|---|
| `/Users/norel/dataplatform/` | Repo root: `.gitignore`, `.claude/settings.local.json`, `chart/`, `app/`. | rare |
| `/Users/norel/dataplatform/chart/` | Helm chart `dataplatform`; its only dependency is the Apache **Ozone** chart 0.2.0 (`charts/ozone-0.2.0.tgz`, `Chart.lock`, `values.yaml`, `templates/_helpers.tpl`, `.helmignore`). Not wired to the API. | rare |
| `/Users/norel/dataplatform/app/backend/` | The API project (uv/pyproject managed). | constant |
| `app/backend/main.py` | Entry point: loads config via `src.platform.environment`, builds the app, exposes module-level `app`; exits 1 on `ConfigurationError`. | on start |
| `app/backend/README.md` | Access model, catalogue, visibility, tables & privileges, blobs & signed URLs, Docker, keys, migrations, tests, layout. **The best single document on the backend.** | reference |
| `app/backend/Dockerfile`, `.dockerignore` | Image for the API; source and dependencies are baked in, so a change needs `docker compose up -d --build backend`. | dev |
| `app/docker-compose.yaml` (repo root) | `backend` + `frontend` + `opa` (1.19.0) + `minio` (chainguard; console on 9001) + `postgres` (18) + a one-shot `bootstrap` container. The API's config is inline under `configs.backend_config`, mounted at `/app/config.yaml`; bootstrap key `BOOTSTRAP_API_KEY` (default `dpk_local_docker_compose_development_key`), DB the `postgres` service (`postgres`/`password` by default). Named volumes `postgres_data`, `sqlite_data`, `minio_data`. Ports overridable via `BACKEND_PORT`/`FRONTEND_PORT`/`OPA_PORT`/`MINIO_PORT`/`MINIO_CONSOLE_PORT`/`POSTGRES_PORT`. | dev |
| `app/backend/config.example.yaml`, `config.yaml` | Template and local (gitignored) configuration. | setup |
| `app/backend/pyproject.toml`, `uv.lock` | Deps, pytest/coverage/ruff settings. | setup |
| `app/backend/bootstrap.sh` | The "administrator" that registers `sqlite-main`, `sqlite-scratch` (files under `/data/sqlite`), `minio-blobs` through the API. Idempotent. | dev |
| `app/backend/alembic.ini` | Alembic settings. Deliberately no `sqlalchemy.url` — it comes from `config.yaml` via `migrations/env.py`. | migrations |
| `app/backend/migrations/versions/` | `0001_baseline`, `0002_system_level_datastores`, `0003_project_tables`, `0004_api_keys`, `0005_project_blobs`, `0006_datastore_visibility`. Revisions never import from `src`. | history |
| `app/backend/policies/dataplatform/` | `authz.rego` and `authz_test.rego` (`opa test policies -v`). | every request |
| `app/backend/src/features/` | One package per thing the platform offers: `users/`, `projects/`, `tables/`, `blobs/`, `datastores/` — each with `model.py`, `service.py`, `router.py` (+ `storage.py` where a feature owns a storage protocol). | every request |
| `app/backend/src/features/datastores/implementations/` | `base.py`, `sqlite.py`, `minio.py`, `_sqlite_privileges.py`. One module per concrete store. | every request |
| `app/backend/src/identity/` | Who the caller is: `keys.py`, `model.py`, `service.py`, `caller.py`, `bootstrap.py`. | every request |
| `app/backend/src/authz/` | What the caller may do: `policy.py`, `opa.py`, `enforcement.py`. | every request |
| `app/backend/src/database/` | `engine.py`, `migrations.py`. Knows nothing about features. | on start |
| `app/backend/src/platform/` | Plumbing: `config.py`, `environment.py`, `exceptions.py`, `error_handlers.py`, `state.py`, `dependencies.py`. Knows nothing about features. | every request |
| `app/backend/tests/` | 19 pytest files, `asyncio_mode = auto`. `conftest.py` boots a real `opa` binary and (for blobs) two real MinIO servers, builds the DB **through the migrations**, and writes users + keys straight into the database. Nothing in the request path is stubbed. `test_project_access.py` is the largest (≈30 tests, five sections). | CI/dev |
| `app/backend/agent-knowledge/repository-explorer/` | **This report.** Tracked in git (the previous report said untracked; it is not). | rare |
| `/Users/norel/dataplatform/app/frontend/` | The console (npm/Vite managed). | constant |
| `app/frontend/index.html`, `vite.config.ts`, `tsconfig.json`, `package.json` | Vite shell, the two dev proxies, strict TS config, scripts `dev`/`build`/`preview`. | dev |
| `app/frontend/README.md` | Why the two proxies exist, what the console assumes about the API, the keyboard table, buffers/workspaces, **"The workspace's pages" (new)**, viewers, the transport, the blob tree, layout. | reference |
| `app/frontend/src/lib/` | `api.ts` (whole API surface + signed-URL rewrite), `authz.ts` (the policy as the console reads it), `sql.ts` (statement building), `media.ts` (signed download URL cache), `format.ts` (bytes/latency/timestamps/timecode), `tree.ts` (blob keys read as a hierarchy), `text.ts` (bytes read as text, 1 MB ceiling). | every render |
| `app/frontend/src/viewers/` | The format abstraction: `viewer.ts` (interface + matchers), `registry.ts` (the only list), `Frame.tsx`, `Transport.tsx`, `Image.tsx`, `Video.tsx`, `Audio.tsx`, `Pdf.tsx`, `Source.tsx` (html/markdown/text), `Unknown.tsx`. Unchanged since `539fdb9`. | every blob render |
| `app/frontend/src/components/` | `Shell.tsx` (Tabline/Cmdline/WorkspaceSegment/Statusline/Canvas), `Rail.tsx`, `WorkspacePane.tsx`, **`MembersPane.tsx` (new)**, `TablePane.tsx`, `BlobPane.tsx`, `ContactSheet.tsx`, `dialogs.tsx`, `Overlay.tsx`, `Palette.tsx`, `Gate.tsx`, `bits.tsx`. Every pane, the rail and the dialogs take a `rights: Rights` prop. | every render |
| `app/frontend/src/vigil/` | The **Vigil** design system, vendored unmodified (`tokens.css`, `components.css`) plus the console's own layer `app.css` (everything prefixed `dp-`, resolves tokens only; **122** `.dp-` rule blocks over **75** distinct `.dp-` selectors —
counted as `grep -cE '^\s*\.dp-'` and `grep -oE '\.dp-[a-z0-9-]+' | sort -u | wc -l`. The
previous report said "117 rules" by some method that does not reproduce; these two do.) | every render |
| `app/frontend/design/` | Design handoff: `VIGIL-DESIGN-SYSTEM.md`, `gallery.html`, `css/tokens.css`, `css/components.css`, `assets/`. **Gitignored**, so local-only reference material. | reference |
| `app/frontend/public/` | `mark.svg`, `favicon.svg`. | rare |
| `app/frontend/node_modules/`, `app/backend/.venv/`, `**/__pycache__/` | ~7k files. Ignore when exploring — a bare glob on `app/backend` is dominated by `.venv`. | never |

## Objects

### Frontend — `src/lib/authz.ts` (the policy mirror)
- `type Permission` — 15 string literals, named exactly as the Rego names them:
  `project.read|update|delete|manage_members|remove_members`,
  `table.read|query|write|create|delete`, `blob.read|download|upload|create|delete`.
- Module-level ladders `viewer`, `editor`, `admin`, `owner` (each spreads the one below) and
  `ROLE_PERMISSIONS: Record<ProjectRole, readonly Permission[]>`.
- `interface Rights { role: ProjectRole | "platform admin" | null; can(p): boolean;
  mayGrant(requested, current): boolean; mayRemove(current): boolean;
  refusal(requested, current): string | null }`.
- The file's own docstring says it is a copy of `policies/dataplatform/authz.rego`, kept rung
  for rung, and that **nothing here grants anything**.

### Frontend — `src/lib/api.ts`
- Types: `Uuid`, `ProjectRole` (`viewer|editor|admin|owner`), `DataType` (`table|blob`),
  `CurrentUser` (carries `project_roles: Record<Uuid, ProjectRole>`), `Project`, `Membership`,
  `CatalogueEntry`, `Table`, `ColumnDefinition` (`name`/`type`/`nullable`/**`primary_key`**),
  `QueryResponse`, `Blob`, `StoredBlob`,
  `BlobView`, `PresignedAccess`, `CreatedBlob`.
- `class ApiError extends Error` — carries `status` and the platform's own sentence.
  `status === 0` means the API did not answer.
- `const api = { … }` — the whole HTTP surface. Module-level mutable `key` set by `setKey`,
  sent as `Authorization: Bearer` on every call.

### Frontend — `src/App.tsx`
- `Selection` = `{kind:"workspace"} | {kind:"members"} | {kind:"table";name} | {kind:"blob";key}`
  (**`members` is new in `ee639a5`**).
- `Buffer` (`id`, `workspaceId`, `selection`), `WorkspaceData` (`tables`, `blobViews`,
  `members`, `loading`), `EMPTY`, `Confirm`, `Overlay` union
  (`palette | new-workspace | new-table | upload | grant | confirm`).
- `KEY_STORE = "dataplatform.key"` in `localStorage`; module-level `bufferSeed`/`nextBufferId`;
  `sameSelection(a,b)`.

### Frontend — components
- `Tab` (`kind: workspace|members|table|blob`), `Mode` (`normal|command|busy`), `SIGIL` map
  (`workspace ◫`, `members ◌`, `table ▦`, `blob ◈`) — `components/Shell.tsx`. **All four kinds
  are now minted.**
- `RailRow` union — `{id:"overview";kind:"overview"} | {id:"members";kind:"members"} |
  table | branch | leaf` — `components/Rail.tsx`.
- `PaletteItem` — `components/Palette.tsx`.
- `TableActions` (`addColumn`, `insertRow`) — `components/TablePane.tsx`.
- `ROLES: ProjectRole[]`, `DraftColumn`, `StepState` (`pending|running|done|failed`),
  module-level `seed`/`nextId` — `components/dialogs.tsx`.
- `ROW_LIMIT = 200` — `lib/format.ts`.

### Frontend — `src/viewers/viewer.ts` (the abstraction) and the viewers
- `ViewerProps { url; stored; blob }`, `ThumbProps extends ViewerProps { onBroken }`,
  `Viewer { kind; types; extensions; render; thumb? }`. A `types` entry ending in `/` matches
  a whole family.

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

- `Pdf.tsx`: `INLINE_LIMIT = 32 * 1024 * 1024`, `SERVED_AS_PDF = "application/pdf"`, inner
  `useRenderable`, component `Document`.
- `Source.tsx`: inner `Printed`, factory `printing(kind, types, extensions, note?)`.
- `Video.tsx`: inner `Screen`; `Audio.tsx`: inner `Deck`.
- `Transport.tsx`: `interface Playback { ready, playing, current, duration, buffered, muted,
  failed }`, `const IDLE: Playback`.
- `src/lib/text.ts`: `TEXT_LIMIT = 1024 * 1024`, `class TooLarge extends Error { size }`,
  `interface Source { text; lossy; lines }`.
- `src/lib/tree.ts`: `Branch<T>`, `Leaf<T>`, `Node<T>`, internal `Draft<T>`, `Run { text, hit }`.

### Backend — authorization vocabulary `src/authz/policy.py`
- `ResourceScope(StrEnum)`: SYSTEM, PROJECT.
- `ResourceType(StrEnum)`: PROJECT, DATASTORE, TABLE, BLOB, USER; `.scope` reads `_SCOPES`;
  an import-time check raises `ConfigurationError` for any unscoped type.
- `Action(StrEnum)`: `project.read/update/delete/manage_members/remove_members`,
  `datastore.create/read/query/update/delete`, `table.create/read/query/write/delete`,
  `blob.create/read/download/upload/delete`, `user.create/read/issue_key`.
- `Subject`, `Resource` (+ computed `scope`), `MembershipChange` (`current_role`,
  `requested_role`, both `ProjectRole | None`; `requested_role=None` means removal),
  `AuthorizationRequest` (optional `membership_change`), `Decision`; Protocols
  `PolicyDecisionPoint`, `ResourceFilter`. `__all__` is declared.

### Backend — configuration `src/platform/config.py`
- `MINIMUM_BOOTSTRAP_KEY_LENGTH = 32`; `DatabaseConfig`, `BootstrapAdminConfig`, `AuthConfig`
  (with `_check_admins_are_distinct` field validator), `OpaConfig`, `AppConfig`.

### Backend — persistence models
- `User` — `src/features/users/model.py` (id, email unique+indexed, name, is_platform_admin,
  creation_date).
- `ApiKey` — `src/identity/model.py` (id, user_id, name, secret_hash unique+indexed,
  creation/expiration/revocation dates).
- `ProjectRole(StrEnum)`, `Project`, `ProjectMember` (composite PK `(project_id, user_id)`) —
  `src/features/projects/model.py`.
- `Table` (`__tablename__ = "projecttable"`) — `src/features/tables/model.py`.
- `Blob` — `src/features/blobs/model.py`.
- `DataStoreVisibility(StrEnum)`, `DataStoreImplementationColumn(TypeDecorator)`, `DataStore`,
  `PERSISTING = {"reveal_secrets": True}` — `src/features/datastores/model.py`.

### Backend — storage contracts
- `src/features/datastores/storage.py`: `DataType(StrEnum)`, `namespace_of(*, project_id)`,
  `DataStoreQuery`, `DataStoreQueryResponse`.
- `src/features/tables/storage.py`: `validate_identifier`,
  `_IDENTIFIER = ^[A-Za-z_][A-Za-z0-9_]{0,62}$`, `_COLUMN_TYPE = ^[A-Za-z][A-Za-z0-9_ (),]{0,63}$`,
  `QueryPrivilege(StrEnum)` (READ_ONLY/READ_WRITE), `ColumnDefinition` (carries
  `primary_key`), **`primary_key_of(columns)`** (the "a key column may not be nullable" rule
  lives here, beside the protocol, not in any implementation), `TableStorage`
  (runtime-checkable Protocol).
- `src/features/blobs/storage.py`: `validate_object_key`,
  `_KEY_SEGMENT = ^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$`, `_MAX_KEY_LENGTH = 1024`,
  `BlobOperation(StrEnum)`, `BlobDescription`, `PresignedAccess`, `BlobStorage` Protocol.
- `implementations/base.py`: `DataStoreImplementationBase(BaseModel, ABC)`.
- `sqlite.py`: `SQLiteDataStore`. `minio.py`: `MinIODataStore` (endpoint, access_key,
  `secret_key: SecretStr`, secure, region, `presigned_url_expiry_seconds` ≤ 7 days),
  `_BUCKET_NAME = ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$`, `_METHOD_FOR`,
  `_ABSENT_CODES = {NoSuchKey, NoSuchBucket, NoSuchObject}`, `_REDACTED = "**********"`.
- `_sqlite_privileges.py`: `type Authorizer`, `_SCHEMA_TABLE = "sqlite_master"`,
  `_READ_ACTIONS`, `_WRITE_ACTIONS`, `_CATALOGUE_ACTIONS`, `_MECHANICS`. Default is DENY.

### Backend — runtime objects
- `OpaPolicyDecisionPoint` (`src/authz/opa.py`), `AccessEnforcer` (`src/authz/enforcement.py`),
  `ApplicationServices` frozen dataclass (`src/platform/state.py`), `IssuedApiKey`
  (`src/identity/service.py`), `DataStoreCatalogueEntry` (`src/features/datastores/catalogue.py`),
  `api_key_scheme = HTTPBearer(scheme_name="API key", auto_error=False)` (`src/identity/caller.py`).
- Exceptions (`src/platform/exceptions.py`): `DataPlatformError` → `ConfigurationError`,
  `SchemaMigrationError`, `ObjectNotFoundError`, `DuplicateObjectError`,
  `AuthenticationError`→`InvalidApiKeyError`,
  `AuthorizationError`→`PolicyDecisionPointError`/`PermissionDeniedError`,
  `StorageError`→`UnsuitableDataStoreError`/`TableProvisioningError`/`BlobProvisioningError`/
  `QueryRefusedError`/`QueryFailedError`.
- Request/response models: users `CurrentUserResponse` (id, email, is_platform_admin,
  project_roles)/`UserResponse`/`CreateUserRequest`/`CreateApiKeyRequest`/`ApiKeyResponse`/
  `IssuedApiKeyResponse`/`CreatedUserResponse`; projects `CreateProjectRequest`/
  `GrantMembershipRequest`/`ProjectMembershipResponse`; tables `CreateTableRequest`/
  `TableQueryRequest`; blobs `CreateBlobRequest`/`BlobView`/`CreatedBlob`/`BlobAccessRequest`
  + `_ACCESS_LIFETIME = timedelta(minutes=15)` + `_ACTION_FOR`; datastores
  `CreateDataStoreRequest`/`UpdateDataStoreVisibilityRequest`.

## Functions

### Frontend

| Function / component | Path |
|---|---|
| `rightsIn(me, project: Uuid \| null) → Rights`, module-private `changeForbidden(mine, requested, current)` | `src/lib/authz.ts` |
| `setKey`, `call<T>`, `readDetail`, `keyPath`, `viaProxy(signed)`, `uploadTo(access, file)` | `src/lib/api.ts` |
| `api.me`, `.listProjects`, `.createProject`, `.listMembers`, `.grantMembership`, `.removeMembership(project, user)`, `.catalogue`, `.listTables`, `.createTable`, `.deleteTable`, `.query`, `.listBlobs`, `.readBlob`, `.createBlob`, `.deleteBlob`, `.blobAccess` | `src/lib/api.ts` |
| `isIdentifier`, `literal`, `insertStatement`, `addColumnStatement`, `selectStatement`, `createTableSketch` (emits `PRIMARY KEY (…)` in the one form the backend uses), `verbOf`, `isRead` | `src/lib/sql.ts` |
| `build`, `flatten`, `keptUnder`, `branchPaths`, `ancestors`, `runs` | `src/lib/tree.ts` |
| `downloadUrl(project, key)`, `forget(project, key)`; `MARGIN_MS = 60_000` | `src/lib/media.ts` |
| `bytes`, `latency`, `stamp`, `clock`, `timecode` | `src/lib/format.ts` |
| `readSource(url, size, signal)` (+ `TEXT_LIMIT`, `TooLarge`) | `src/lib/text.ts` |
| `App()` — holds all state; inner `say`, `report`, `signIn`, `signOut`, `loadWorkspace`, `loadPlatform`, `goTo`, `openInNewBuffer`, `duplicateBuffer`, `forgetSelection`, `closeBuffer`, `switchWorkspace`, `openRow(row, newTab)`, `runTyped`, the single `keydown` dispatcher, and the `commands` registry | `src/App.tsx` |
| `Tabline`, `Cmdline`, `WorkspaceSegment`, `Statusline`, `Canvas` | `src/components/Shell.tsx` |
| `railRows(tables, visible)` (emits `overview` + `members` first), module-private `isPage(row)`, `Name`, `Rail` | `src/components/Rail.tsx` |
| `WorkspacePane` — contents only now; the `members` `Fact` is pressable and calls `onOpenMembers` | `src/components/WorkspacePane.tsx` |
| **`MembersPane`** — the membership page; per-row `remove` gated by `rights.can("project.remove_members")` and disabled with `rights.refusal(null, member.role)` as its `title` | `src/components/MembersPane.tsx` |
| `TablePane` (inner `run(text,{quiet})`, `reload`) | `src/components/TablePane.tsx` |
| `BlobPane` (inner `replace`; calls `resolve(...)` then renders `viewer.render`) | `src/components/BlobPane.tsx` |
| `ContactSheet`, `Shot` | `src/components/ContactSheet.tsx` |
| `useSubmit`, `NewWorkspaceDialog`, `GrantDialog`, `NewTableDialog`, `AddColumnDialog`, `InsertRowDialog`, `UploadDialog`, `ConfirmDialog` | `src/components/dialogs.tsx` |
| `useOverlay`, `Dialog`, `Modal` | `src/components/Overlay.tsx` |
| `Palette`, `Row` | `src/components/Palette.tsx` |
| `Gate` | `src/components/Gate.tsx` |
| `Head`, `Empty`, `Loading`, `Problem`, `Field`, `Sketch`, `KV`, `Fact` (now optionally a `<button class="vg-fact dp-fact-link">`) | `src/components/bits.tsx` |
| `claimsType`, `claimsName` | `src/viewers/viewer.ts` |
| `resolve(contentType, key) → Viewer`; module-level `viewers` array, order load-bearing | `src/viewers/registry.ts` |
| `Frame`, `Undecodable` | `src/viewers/Frame.tsx` |
| `useTransport(ref)`, `Transport` | `src/viewers/Transport.tsx` |
| `Screen`/`video`, `Deck`/`audio`, `useRenderable`+`Document`/`pdf`, `Printed`+`printing`/`html`,`markdown`,`text` | `src/viewers/{Video,Audio,Pdf,Source}.tsx` |
| root render into `#root` (StrictMode; imports the three CSS layers in order) | `src/main.tsx` |

### Backend

| Function | Path |
|---|---|
| `main()`, module-level `app` | `main.py` |
| `create_app(*, config)`, inner `lifespan`, `GET /` handler `default()`; `_API_DESCRIPTION` | `src/app.py` |
| `load_config(*, path)`, `AuthConfig._check_admins_are_distinct` | `src/platform/config.py` |
| `configuration_path()`, `load_configuration()`; `CONFIG_PATH_VARIABLE = "DATAPLATFORM_CONFIG"`, `DEFAULT_CONFIG_PATH = Path("config.yaml")` | `src/platform/environment.py` |
| `create_database_engine`, `open_session` | `src/database/engine.py` |
| `upgrade_to_head`, `_alembic_configuration` | `src/database/migrations.py` |
| `get_services`, `get_session`, `get_enforcer`, `get_configuration` (+ `Services`/`DatabaseSession`/`Enforcer`/`Configuration` aliases) | `src/platform/dependencies.py` |
| `register_error_handlers(*, app)` + 10 handlers (`_handle_invalid_api_key`, `_handle_permission_denied`, `_handle_policy_engine_down`, `_handle_not_found`, `_handle_duplicate`, `_handle_query_refused`, `_handle_query_failed`, `_handle_unsuitable_datastore`, `_handle_blob_provisioning_failure`, `_handle_provisioning_failure`) | `src/platform/error_handlers.py` |
| `generate_key()`, `digest_of(*, key)`; `KEY_PREFIX = "dpk_"`, `_SECRET_BYTES = 32` | `src/identity/keys.py` |
| `current_user`, `current_subject`, `api_key_scheme` | `src/identity/caller.py` |
| `issue_api_key`, `authenticate`, `_is_usable`, `list_api_keys`, `revoke_api_key` | `src/identity/service.py` |
| `ensure_bootstrap_admins`, `_ensure_administrator`, `_ensure_key`, `_ensure_key_is_still_theirs`; `BOOTSTRAP_KEY_NAME = "bootstrap"` | `src/identity/bootstrap.py` |
| `OpaPolicyDecisionPoint.decide/filter_allowed/_query/check_reachable` | `src/authz/opa.py` |
| `AccessEnforcer.ensure_allowed(**, membership_change=None)`, `.is_allowed`, `.keep_allowed` | `src/authz/enforcement.py` |
| `create_user`, `get_user`, `locate_user_by_email` (returns `User \| None`), `find_user_by_email` (raises), `list_users`, `describe_subject` | `src/features/users/service.py` |
| `create_project`, `get_project`, `list_projects`, `roles_of_user`, `member_role`, `set_member_role`, `remove_member`, `list_members` | `src/features/projects/service.py` |
| `_storage_behind`, `get_table`, `list_tables`, `create_table`, `delete_table`, `run_query` | `src/features/tables/service.py` |
| `_storage_behind`, `get_blob`, `list_blobs`, `create_blob`, `describe_blob`, `grant_access`, `delete_blob` | `src/features/blobs/service.py` |
| `create_datastore`, `get_datastore`, `list_datastores`, `set_visibility`, `delete_datastore`, `run_query` | `src/features/datastores/service.py` |
| `_describe`, `list_catalogue` | `src/features/datastores/catalogue.py` |
| `build_authorizer` (inner `authorize`), `is_refusal` | `src/features/datastores/implementations/_sqlite_privileges.py` |
| `_unreachable`, `MinIODataStore._reveal_secret_key_only_to_the_database/_client/_bucket_for/_describe/ensure_namespace/delete_blob/describe_blob/presign/query/get_data_type` | `src/features/datastores/implementations/minio.py` |
| `SQLiteDataStore._database_for/_connect/create_table/drop_table/query_table/query/get_data_type` | `src/features/datastores/implementations/sqlite.py` |
| `namespace_of(*, project_id)` → `p<uuid.hex>` | `src/features/datastores/storage.py` |
| `create_users_router` (+ `_describe_key`, `_describe_issued_key`, `_describe_user`), `create_projects_router`, `create_tables_router`, `create_blobs_router`, `create_datastores_router` (each with a local `_as_resource` helper) | `src/features/*/router.py` |

### Rego — `policies/dataplatform/authz.rego`
- Rule sets `viewer_permissions ⊂ editor_permissions ⊂ admin_permissions ⊂ owner_permissions`,
  `role_permissions`.
- `default allow := false`; `allow if { is_allowed(...) ; not membership_change_forbidden }`.
- `decision := {allow, reason}`; six `reason` rules (system scope · not a member · role does
  not grant · may manage but only an owner grants owner · owner cannot be demoted · owner
  cannot be removed).
- `allowed_resource_ids contains resource.id` — the filter used by every listing.
- `is_allowed(subject,_,_) if subject.is_platform_admin`; `is_allowed(subject,action,resource)`
  via `subject.project_roles[resource.project_id]`.
- `default membership_change_forbidden := false` plus two rules: only an owner may create an
  owner; an owner may never be lowered or removed (`requested_role == null` is removal).
- `project_role := input.subject.project_roles[input.resource.project_id]` — used only to
  explain a denial.

### HTTP surface (what the console consumes)

- `GET /` (health, no credentials).
- Users: `GET /users/me` (returns `project_roles`), `POST|GET /users/me/api-keys`,
  `DELETE /users/me/api-keys/{key_id}`, `POST /users/`, `GET /users/`,
  `POST /users/{user_id}/api-keys`.
- Projects: `POST /projects/`, `GET /projects/`, `GET /projects/{id}`,
  `GET /projects/{id}/members`, `PUT /projects/{id}/members`,
  `DELETE /projects/{id}/members/{user_id}` (204).
- Tables (`/projects/{project_id}/tables`): `POST /`, `GET /`, `GET /{table_name}`,
  `POST /{table_name}/query`, `DELETE /{table_name}`.
- Blobs (`/projects/{project_id}/blobs`): `POST /`, `GET /?prefix=`, `GET /{key:path}`,
  `POST /{key:path}/access`, `DELETE /{key:path}`.
- Datastores: `GET /datastores/query`, `GET /datastores/catalogue`, `POST /datastores/`,
  `GET /datastores/`, `GET /datastores/{name}`, `PATCH /datastores/{name}` (visibility),
  `DELETE /datastores/{name}`.

## Dependencies

### Frontend (`app/frontend/package.json`)
- Runtime: **react** ^19.1, **react-dom** ^19.1. Nothing else — no router, no query library,
  no CSS framework, **no pdf.js** (the browser's own pdf reader is used through an `<iframe>`).
- Dev: **vite** ^7, **@vitejs/plugin-react** ^5, **typescript** ^5.7, `@types/node` ^26.2,
  `@types/react` ^19.1, `@types/react-dom` ^19.1.
- Build: `tsc -b && vite build`. TS is `strict` with `noUnusedLocals`, `noUnusedParameters`,
  `noFallthroughCasesInSwitch`, `verbatimModuleSyntax`, `isolatedModules`, `noEmit`;
  target/lib ES2022 + DOM.
- Browser APIs leaned on: `fetch` + `AbortController`, `TextDecoder` (including `{fatal:true}`),
  `URL.createObjectURL`/`revokeObjectURL`, `HTMLMediaElement` events + `buffered` TimeRanges,
  the Fullscreen API, `localStorage`, `DataTransfer` (drag-and-drop upload).
- Runtime services it needs: the **API on :8000** and **MinIO on :9000**, both reached through
  the Vite dev proxies (`/api` and `/blob`).

### Backend (`app/backend/pyproject.toml`, Python ≥3.14, uv)
- **alembic** ≥1.19.1, **fastapi** ≥0.136.3, **pydantic** ≥2.13.4, **sqlmodel** ≥0.0.38
  (+SQLAlchemy), **httpx** ≥0.28.1, **loguru** ≥0.7.3, **pyyaml** ≥6.0.3,
  **email-validator** ≥2.3.0, **minio** ≥7.2.20, **urllib3** ≥2.7.0 (named explicitly so the
  MinIO datastore's direct `HTTPError` import survives minio changing its HTTP client).
- stdlib `sqlite3` (including the authorizer API), `secrets`, `hashlib`, `asyncio.to_thread`
  (every MinIO call is blocking and is offloaded).
- Dev group: `fastapi[standard]`, `pytest` ≥9.1.1, `pytest-asyncio` ≥1.4 (auto mode),
  `pytest-cov` ≥7.1 (`fail_under = 80`, `branch = true`), `ruff` ≥0.16.3
  (`select = E,F,W,I,UP,B,SIM,RET,C4,S`, line-length 96, `target-version = py314`;
  per-file ignores for `tests/*` and `migrations/versions/*`), `ty` ≥0.0.39.

### External services / tooling
- **Open Policy Agent** (`openpolicyagent/opa:1.19.0`, or a local `opa` binary) serving
  `dataplatform/authz/decision` and `dataplatform/authz/allowed_resource_ids`. Required at
  runtime — without it everything guarded is a 503.
- **MinIO** (`quay.io/minio/minio:latest`), API on 9000, console on 9001. Needed for blobs;
  the blob tests run **two** independent servers.
- **Database**: PostgreSQL only, as a `postgresql+psycopg://` URL; `DatabaseConfig` rejects anything else. Tests start a `postgres:18` container (or use `TEST_DATABASE_URL`) with a fresh database per test.
- **Docker Compose** for the whole stack; **curl** image for the seeding container.
- **Helm/Kubernetes**: `chart/` depends on the Apache Ozone chart.
- No external identity provider — the platform issues its own credentials.

## Notable design notes / gotchas

### The workspace's two pages (new in `ee639a5`)
- A workspace has **two pages of its own**: `overview` (what it holds) and `members` (who may
  reach it). Both are ordinary buffers, so a members page can sit in its own tab beside a table.
- The rail lists them under a `workspace` group; `railRows` emits them and `isPage(row)` is how
  the rail draws that group, so **adding a third page means touching `railRows` and nothing else**.
- The overview's fact band still *counts* members, and that tile is the way to the page
  (`Fact` renders as a button when given `onOpen`).
- Reached three ways: the rail row, the `members` `Fact`, or the `:members` command.
  `Shell.tsx`'s `members` sigil is `◌`.
- `MembersPane` shows `grant access` disabled unless `project.manage_members`, and a per-row
  `remove` that only appears with `project.remove_members` and is disabled (with the refusal as
  `title`) when `rights.refusal(null, member.role)` is non-null — i.e. for owners.
- Removal confirmation text and the `api.removeMembership` + `loadWorkspace` sequence live in
  `App.tsx`, not in the pane.

### Membership (the policy)
- **`project.manage_members` and `project.remove_members` are separate actions.** An admin holds
  only the first. `PUT /members` asks the first, `DELETE /members/{user_id}` asks the second.
- **Both membership endpoints send a `MembershipChange`** carrying the role the member holds
  *now* and the role they are asked to *end up* holding. Removal is `requested_role = None` —
  "being put out of a project is being taken below every rung of the ladder at once" — which is
  why one Rego rule covers demotion and removal.
- **Both endpoints read the member before the decision and insist on them after it.**
  `grant_membership` uses `users_service.locate_user_by_email` (returns `None` rather than
  raising) and only raises `ObjectNotFoundError` *after* `ensure_allowed` passes, so a refusal
  cannot be used to enumerate which addresses the platform knows. `remove_membership` does the
  same with `member_role`.
- `remove_member` **deletes** the `ProjectMember` row rather than emptying it, "because a member
  holding no role and no member at all are the same thing to the policy".
- The console mirrors all of this in `lib/authz.ts` — `changeForbidden` is the two Rego rules
  transliterated, `refusal()` returns the sentence to show, and `mayGrant`/`mayRemove` are just
  `refusal(...) === null`. `GrantDialog` matches the typed address against the member list to
  learn `current`, disables the `<option>`s it may not grant, and prints the refusal before
  submitting.
- **`lib/authz.ts` is a copy and copies drift.** The file says so at the top and asks to be kept
  rung for rung with `authz.rego`, in the same order. If you change one, change the other.

### Frontend — buffers and tabs
- **Clicking a table or blob re-points the tab in hand** (`goTo`). It never mints a tab and never
  jumps to another tab holding the same thing.
- **A tab is only born by being asked for**: `+`, `:new tab`, ⌘/Ctrl-click or middle-click a rail
  row, or `⇧↵` on the rail cursor. `+`/`:new tab` *duplicate* the current buffer
  (`duplicateBuffer`); the modifier-click opens the row picked (`openInNewBuffer`). Either way
  the new tab lands **beside** the one it came from.
- **The same object may sit in two tabs at once**, deliberately.
- **Deleting sweeps every buffer** (`forgetSelection`), and the affected tabs fall back to the
  workspace overview rather than closing.
- `openInNewBuffer` mints the id **outside** the state updater on purpose: an updater that mints
  an id and sets other state is not pure, and StrictMode runs it twice.
- The workspace is a property of the *buffer*, not the window, so two tabs can sit in two
  workspaces; that is why the workspace picker lives in the statusline. Workspace data is cached
  per workspace in `data: Record<Uuid, WorkspaceData>`.
- **One keyboard dispatcher** (a single `window` `keydown` listener in `App.tsx`) and **one
  command registry** shared by `:` and ⌘K. Keys: `1`–`9` buffers, `j`/`k` rail, `↵` open/fold,
  `⇧↵` open in a new tab, `:` command line, `/` or `f` find, `⌘K` palette, `⌘↵` run statement,
  `esc` dismiss. Commands: `:new workspace`, `:new table`, `:upload`, `:add column`,
  `:insert row`, `:find`, `:new tab`, `:close`, `:grant access`, **`:members`**, `:reload`,
  `:density`, `:gloss`, `:forget key`. Every command that changes something checks
  `rights.can(...)` first and says why not.
- The command line also accepts a bare **number** to jump to that buffer, then exact-match, then
  prefix-match, then object-name match.
- Membership is loaded in a *separate* try/catch inside `loadWorkspace`, because a viewer may be
  refused `GET /members` and that must not empty the rest of the workspace.
- **A table's shape is read with `SELECT * FROM <table> LIMIT 0`** and taken from
  `metadata.columns` — `PRAGMA` is refused by the privilege the query endpoint connects with,
  and that is correct.
- `TablePane.run(text, {quiet})` — a statement run from a dialog reports its refusal inside that
  dialog.
- **`stored: null` is a normal state** (recorded, never filled) and is rendered as a dashed frame
  / plain sentence, never a broken image.
- Blob keys are single strings; the rail *infers* a tree from the slashes. Branches disappear with
  their last leaf. Search matches the **whole key**, highlights per-segment runs, ignores folding,
  and the heading reports `[shown of total]`.
- The API key is kept in `localStorage` under `dataplatform.key`; `:forget key` clears it.
  `ApiError` with `status === 0` flips the statusline to "api unreachable". A non-JSON body is
  reported as "the `/api` proxy is not in front of the platform".
- Signed download URLs are cached per `project/key` in `lib/media.ts` and re-minted 60 s before
  they lapse; `forget()` is called after a replace or delete.
- **Two dev proxies, both deliberate** (`vite.config.ts`). `/api` → `127.0.0.1:8000`
  (`changeOrigin: true`) because the API sets **no CORS headers**. `/blob` → `127.0.0.1:9000`
  (`changeOrigin: false`) with `headers: { Host: "minio:9000" }` set **on the proxy options, not
  in a `proxyReq` handler** — a request carrying `Expect: 100-continue` has already flushed its
  headers by then, which would break uploads over roughly a megabyte and nothing smaller.
  `viaProxy()` keeps path and query byte-for-byte, because they carry the AWS signature. For a
  real deployment neither proxy is the answer.
- **Known deviation from the design handoff:** `--vg-fg-muted` is overridden in
  `src/vigil/app.css` from `#5A5852` to `#7C7A74` for contrast (≈2.8:1 → 4.5:1), which §13 of
  `VIGIL-DESIGN-SYSTEM.md` invites. `design/` is gitignored, so the vendored copies in
  `src/vigil/` are the ones that ship.

### Frontend — viewers
- **One list, one decision.** `resolve(contentType, key)` in `registry.ts` is the whole of the
  console's knowledge about formats. Panes call it and render `viewer.render` / `viewer.thumb`;
  they contain no format conditionals.
- **Order in `viewers` is load-bearing:** an exact type must precede its family, or `text/` would
  swallow `text/html`. Current order: `image, video, audio, pdf, html, markdown, text`.
- **Type first, name second, never mixed.** `claimsType` is tried across *all* viewers before
  `claimsName` is tried across any; `claimsName` refuses a dot living in a directory segment.
  `unknown` claims nothing and can never steal a format.
- **The pdf viewer is where the registry's vote and the browser's vote diverge.**
  `useRenderable`: if the header already says `application/pdf`, point the iframe at the signed
  URL; otherwise fetch once, check the leading `%PDF-` bytes, and hand back a
  `URL.createObjectURL(new window.Blob([...], {type: "application/pdf"}))`. The signature check is
  why the iframe needs no `sandbox`. Above 32 MB it refuses and offers "open bytes". It **resets
  its state unconditionally at the top of the effect**, because the component is reused across
  blobs.
- **HTML is shown as source and never rendered** — a blob is a stranger's bytes and the page holds
  an API key.
- `Source` is the only viewer that must hold the whole blob, hence the only ceiling (1 MB).
  `readSource` decodes twice: strict (`{fatal:true}`) to learn whether it was text, then lenient
  to have something to show; `lossy` is surfaced rather than silently printing `�`.
- **The transport is built, not borrowed.** The seek bar stays an `<input type="range">` under the
  paint so arrows/Home/End/screen-reader semantics survive; its track is three layers (`--done`,
  `--ahead`) — the middle layer is the only place the console says whether a stall is the network
  or the file. `useTransport` is keyed on the ref alone; `duration` of `Infinity`/`NaN` is carried
  through as-is; `play()` rejection sets `failed` rather than throwing.
- `Undecodable` covers the QuickTime case (a `.mov` carrying H.265 Safari plays and Chrome will
  not) — reported as a browser limit, not damage. Solid frame means empty, dashed (`is-hollow`)
  means deliberately not there.

### Backend
- `src/app.py` is the only module naming OPA; everything else depends on
  `PolicyDecisionPoint`/`ResourceFilter`. Authentication has no such seam by design.
- **Layout rule 1:** a feature owns its storage protocol. **Rule 2:** no `__init__.py`
  re-exports anything, so the import graph stays acyclic. **Rule 3:** `platform` and `database`
  know nothing about features. `identity` imports `features.users` and `authz` imports
  `features.projects.model` — the only two crossings, and both are the domain being honest.
- `Resource.scope` is computed from the type, never supplied.
- **Ask the policy before the database.** Datastores and users always did; `GET /{key:path}`,
  `POST /{key}/access` and `DELETE /{key}` on blobs, and `GET /{table_name}`,
  `POST /{table_name}/query` and `DELETE /{table_name}` on tables do too, so a refusal cannot
  reveal whether a name exists. `POST /tables/` and `POST /blobs/` still call
  `projects_service.get_project` first (the project id is in the URL and a missing project is a
  legitimate 404).
- `POST /projects/` performs **no** enforcer call: any authenticated user may create a project
  and becomes its `owner`.
- The three `/users/me/...` key endpoints are deliberately **not** put to the policy.
- `GET /datastores/query` and `/catalogue` are declared before `/{datastore_name}`, so the literal
  paths win. **`GET /datastores/catalogue`** is the deliberate exception to the system scope: any
  authenticated caller may learn names/data types/descriptions, built field by field into
  `DataStoreCatalogueEntry` so a new credential field cannot leak.
- **`visibility`** (`public`/`private`, default `public`) decides only whether a datastore appears
  in the catalogue. It is **hidden, not protected** — the policy never consults it.
- The table query endpoint is the only place `AccessEnforcer.is_allowed` is used: `table.write` is
  asked first and, if refused, `table.query` is *enforced*; the answer picks the `QueryPrivilege`.
  A decision-point failure raises rather than downgrading.
- SQLite: a namespace is a sibling database file (`warehouse__p<hex>.db`). A read-write caller
  **can** read `sqlite_master` within their own namespace, because `ALTER TABLE` requires it;
  documented, not a choice.
- MinIO: `secret_key` is a `SecretStr` **and** has a field serializer that reveals it for exactly
  one destination (the dump in `features/datastores/model.py` that writes the row). `_bucket_for`
  re-checks the derived name against `_BUCKET_NAME` even though the platform derives it.
  `_unreachable` turns an `HTTPError` from the client into a platform `StorageError`.
- **Blob keys have a grammar.** `validate_object_key` splits on `/` and requires each segment to
  match `^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$`, refusing empty segments, `.` and `..`,
  leading/trailing slashes, and anything over 1024 characters. Keys are unique **per project**,
  not per datastore; a blob does not move between datastores. Wrong-type datastore → 400, unknown
  name → 404, unreachable store → **502**.
- Signed URLs cannot be withdrawn, so they are minted for 15 minutes (`_ACCESS_LIFETIME`), and the
  shorter of that and the datastore's `presigned_url_expiry_seconds` wins. Deleting goes through
  the API, never through a signed URL.
- A presigned URL points at `minio:9000`; from the host, follow one with
  `curl --resolve minio:9000:127.0.0.1 "<url>"` (or, in the console, through the `/blob` proxy).
- **Authentication is deliberately shapeless.** `api_key_scheme` is `HTTPBearer(auto_error=False)`
  so FastAPI does not answer a missing header itself; missing, unknown, revoked and expired keys
  all surface as `InvalidApiKeyError` and are answered identically.
- **Bootstrap administrators must be distinct.** `AuthConfig._check_admins_are_distinct` rejects a
  list where two share an address or a key. `ensure_bootstrap_admins` runs on every start; changing
  the configured key rotates it (old one revoked), while re-using a revoked or somebody else's key
  raises `ConfigurationError` and stops the process.
- Autogenerated revisions render the implementation column as
  `src.datastore.DataStoreImplementationColumn()` — replace with `sa.JSON()`; revisions must never
  import from `src`. Revisions target PostgreSQL only: quote `"user"` in raw SQL, and create a new
  `sa.Enum` type before `add_column`.
- Port 8000 collision: a host `fastapi dev` beats the published container port on localhost; use
  `BACKEND_PORT=8001 docker compose up -d`. The compose metadata database is the `postgres`
  service (`postgres_data` volume), published on `localhost:5432`.

### Exploration gotchas
- Globbing `app/backend` without a subdirectory prefix returns thousands of `.venv` files and gets
  truncated before reaching `src/`. Glob `src/**/*.py` and `tests/*.py` instead.
- `tests/__pycache__/` holds stale `.pyc` files for tests that no longer exist
  (`test_google_identity`, `test_zz_probe`). They are not source.
