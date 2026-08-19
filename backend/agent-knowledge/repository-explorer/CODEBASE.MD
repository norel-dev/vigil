# DataPlatform API (`dataplatform` repo, `app/` package)

## Commit

- Repository root: `/Users/norel/dataplatform` (git dir lives there; the API lives in `/Users/norel/dataplatform/app`)
- Branch at time of writing: `project-tables`
- HEAD commit: `d7e51d1` — "Let a project create tables in a datastore that holds tables, and run DDL and DML against them at the privilege their role earns, with creating and dropping reserved to the platform and every other project out of reach."
- Preceding commits: `bb4b922` (Alembic migrations), `7454e18` (system level datastores), `7a5db4f` (Datastores).
- **IMPORTANT:** this report describes the *working tree*, which at the time of writing carries a large uncommitted change on top of `d7e51d1`: **Google OAuth authentication was ripped out and replaced with platform-issued API keys**. Untracked/new: `src/auth/api_keys.py`, `src/services/api_keys.py`, `src/services/bootstrap.py`, `migrations/versions/0004_api_keys.py`, `tests/test_api_keys.py`. Deleted: `src/auth/google.py`, `src/auth/identity.py`, `tests/test_google_identity.py`. If that work has since been committed, diff from `d7e51d1` onwards.

## Description

A Python 3.14 FastAPI application ("DataPlatform API") that abstracts management of data stored across multiple underlying stores. Authorization is fully delegated to an external **Open Policy Agent (OPA)** Rego policy; authentication is by **API keys the platform issues itself**; the database schema is owned by **Alembic** revisions applied automatically at startup.

- Languages: Python (~34 source files under `src/`, 10 test files, 4 migration revisions), Rego (2 files), YAML/INI/TOML.
- Roughly 55 source files outside `.venv`.
- Core ideas:
  - A caller presents `Authorization: Bearer dpk_...`; the platform stores only a SHA-256 digest of each key and recognises a caller by looking that digest up.
  - **The platform has two levels (scopes)**, and every resource type declares which it belongs to:
    - `system` — **datastores** and **users**. Only platform administrators may act on them.
    - `project` — **projects** and the **tables** under them. Governed by the caller's `ProjectRole` in the owning project.
  - The API never decides permissions itself: it builds `AuthorizationRequest` documents (including a computed `scope`) and asks OPA. Fails **closed** (503) if OPA is unreachable.
  - List endpoints filter through a single OPA `allowed_resource_ids` call rather than re-implementing rules in Python.
  - A project reaches data through a **table** it owns inside a datastore. Query privilege (read-only vs read-write) is chosen from the policy's answer, then **enforced by the database engine**, never by parsing SQL.
  - Schema lives in `migrations/versions/`; `src.schema.upgrade_to_head` runs at lifespan start, stamping pre-Alembic databases with the baseline first, then `ensure_bootstrap_admins` runs.
- Entrypoint: `uv run fastapi dev main.py`; only env var read anywhere is `DATAPLATFORM_CONFIG` (defaults to `./config.yaml`), read solely by `src/environment.py`.

## What changed since the previous report (`bb4b922`)

1. **Tables added** (commit `d7e51d1`): `src/table.py`, `src/storage.py`, `src/sqlite_privileges.py`, `src/services/tables.py`, `src/endpoints/tables.py`, revision `0003_project_tables`, tests `test_table_access.py` / `test_table_storage.py`. `ResourceType.TABLE` and five `table.*` actions.
2. **Query/response models moved** out of `src/datastore.py` into `src/storage.py` (`DataStoreQuery`, `DataStoreQueryResponse`), joined by `ColumnDefinition`, `QueryPrivilege`, the `TableStorage` protocol and `validate_identifier`.
3. **`SQLiteDataStore` became table storage**: per-project namespaces are separate SQLite files (`warehouse__p<hex>.db`), and per-query privilege is realised with SQLite's authorization callback (`src/sqlite_privileges.py`).
4. **Google auth removed, API keys introduced** (uncommitted): `ApiKey` model, `src/auth/api_keys.py` (generate/digest), `src/services/api_keys.py` (issue/authenticate/list/revoke), `src/services/bootstrap.py` (bootstrap admins from config), revision `0004_api_keys`. `User.google_subject` dropped. `AuthConfig` now holds only `bootstrap_platform_admins`; `GoogleConfig` gone.
5. **Users became a system-scoped resource** with `user.create` / `user.read` / `user.issue_key` actions and a `/users/` management surface, plus self-service `/users/me/api-keys`.
6. **Router factories lost their `auth` argument**; auth dependencies are now module-level (`CurrentUser`, `CurrentSubject`) rather than built per-app. `AuthenticationDependencies` and `ApplicationServices.identity_provider` are gone.
7. **New exceptions**: `DuplicateObjectError`, `InvalidApiKeyError` (replacing `InvalidTokenError`/`IdentityProviderUnavailableError`), and a `StorageError` family (`UnsuitableDataStoreError`, `TableProvisioningError`, `QueryRefusedError`, `QueryFailedError`).

## File Structure

| Path | Description | Usage frequency |
|---|---|---|
| `/Users/norel/dataplatform/` | Repo root; git dir, `.gitignore`, Helm chart. | rare |
| `/Users/norel/dataplatform/chart/` | Helm chart `dataplatform` whose only dependency is the Apache **Ozone** chart 0.2.0 (`charts/ozone-0.2.0.tgz`, `Chart.lock`, `values.yaml`, `templates/_helpers.tpl`). Not wired to the API yet. | rare |
| `/Users/norel/dataplatform/app/` | The API project (uv/pyproject managed). | constant |
| `app/main.py` | Entry point: loads config via `src.environment`, builds the app, exposes module-level `app`; exits 1 on `ConfigurationError`. | on start |
| `app/alembic.ini` | Alembic settings. Deliberately has **no `sqlalchemy.url`** — the URL comes from `config.yaml` via `migrations/env.py`. | migrations |
| `app/migrations/` | Schema history: `env.py`, `script.py.mako`, `README`, `versions/`. | on start / dev |
| `app/migrations/versions/0001_baseline.py` | Photograph of the pre-Alembic schema. Imports nothing from `src`. | history |
| `app/migrations/versions/0002_system_level_datastores.py` | Drops `catalog`, and `datastore.owner_id`/`project_id` via `batch_alter_table`. | history |
| `app/migrations/versions/0003_project_tables.py` | Creates `projecttable` (+3 indexes, unique `(project_id, name)`). | history |
| `app/migrations/versions/0004_api_keys.py` | Creates `apikey` (unique index on `secret_hash`), drops `user.google_subject`. | history |
| `app/pyproject.toml`, `app/uv.lock`, `app/.python-version` | uv project metadata, locked deps, Python pin (3.14). | rare |
| `app/config.example.yaml` | Template configuration (database / auth.bootstrap_platform_admins / opa). Copy to `config.yaml` (gitignored). | setup |
| `app/docker-compose.yaml` | Runs `openpolicyagent/opa:1.19.0` on :8181 with `./policies` mounted read-only, console decision logs, healthcheck. | dev |
| `app/README.md` | Access model, tables & privilege model, SQLite caveats, API keys, migrations, running, layout. The best single document in the repo. | reference |
| `app/policies/dataplatform/` | The Rego policy (`authz.rego`) and its tests (`authz_test.rego`, run with `opa test policies -v`). | every request (via OPA) |
| `app/src/` | The application package. | constant |
| `app/src/auth/` | Who the caller is: `api_keys.py` (generate/digest), `dependencies.py` (bearer scheme + `current_user`/`current_subject`). | every request |
| `app/src/authz/` | What the caller may do: `policy.py` (vocabulary/scopes/protocols), `opa.py` (OPA HTTP client), `enforcement.py` (`AccessEnforcer`). | every request |
| `app/src/services/` | Storage/business logic over SQLModel sessions: `users.py`, `api_keys.py`, `bootstrap.py`, `projects.py`, `tables.py`, `datastores.py`. | every request |
| `app/src/endpoints/` | HTTP surface: router factories `users.py`, `projects.py`, `tables.py`, `datastores.py`, plus `errors.py` exception handlers. | every request |
| `app/tests/` | Pytest suite (`asyncio_mode = auto`, `testpaths = ["tests"]`). `conftest.py` boots a real `opa` binary, builds the DB **through the migrations**, and writes users + keys straight into the database. Nothing in the request path is stubbed. | CI/dev |
| `app/.claude/` | Claude Code settings (`settings.json` enables the `software-engineering@norels-marketplace` plugin). | rare |
| `app/agent-knowledge/` | This report (untracked). | rare |
| `app/.venv/` | Local virtualenv (gitignored, ~4k files). Ignore when exploring. | never |

## Objects

### Configuration — `app/src/config.py`
- `DatabaseConfig` (url, echo), `BootstrapAdminConfig` (email, name, api_key with `MINIMUM_BOOTSTRAP_KEY_LENGTH = 32`), `AuthConfig` (bootstrap_platform_admins + `_check_admins_are_distinct` validator), `OpaConfig` (url, decision_path, filter_path, request_timeout_seconds), `AppConfig` (database, auth, opa). All pydantic `BaseModel`.

### Environment — `app/src/environment.py`
- Constants `CONFIG_PATH_VARIABLE = "DATAPLATFORM_CONFIG"`, `DEFAULT_CONFIG_PATH = Path("config.yaml")`. The only module that reads `os.environ`; shared by `main.py` and `migrations/env.py`.

### Persistence models — `app/src/models.py` (SQLModel tables)
- `DataType(StrEnum)`: TABLE, BLOB.
- `ProjectRole(StrEnum)`: viewer, editor, admin, owner (ordering meaningful; permission mapping lives in Rego).
- `User` (id UUID, email unique+indexed, name, is_platform_admin, creation_date) — **no `google_subject`**.
- `ApiKey` (id, user_id FK+index, name, secret_hash unique+index, creation_date, expiration_date|None, revocation_date|None).
- `Project` (id, name unique, description, creation_date) — owner is the `OWNER` member.
- `ProjectMember` (project_id + user_id composite PK, role, creation_date).

### Tables — `app/src/table.py`
- `Table` (SQLModel, `__tablename__ = "projecttable"`): id, name (index), project_id FK, datastore_name FK, description, creation_date; unique `(project_id, name)`.

### Storage contracts — `app/src/storage.py`
- `validate_identifier(*, name, kind)`; regexes `_IDENTIFIER`, `_COLUMN_TYPE`.
- `QueryPrivilege(StrEnum)`: READ_ONLY, READ_WRITE.
- `ColumnDefinition` (name, type, nullable) with validators for both name and type.
- `DataStoreQuery` (query), `DataStoreQueryResponse` (data, metadata, latency).
- `TableStorage` (`@runtime_checkable` Protocol): `create_table`, `drop_table`, `query_table`.

### SQLite privilege rules — `app/src/sqlite_privileges.py`
- `type Authorizer`, `build_authorizer(*, table, privilege)`, `is_refusal(*, error)`; constants `_SCHEMA_TABLE`, `_READ_ACTIONS`, `_WRITE_ACTIONS`, `_CATALOGUE_ACTIONS`, `_MECHANICS`. Default is DENY for anything unrecognised.

### Datastores — `app/src/datastore.py`
- `DataStoreImplementationBase(BaseModel, ABC)` with abstract `get_data_type()` and `query()`; `implementation` is the discriminator.
- `SQLiteDataStore` (`implementation: Literal["sqlite"]`, `sqlite_connection_string`) — also satisfies `TableStorage`: `_database_for`, `_connect`, `query`, `create_table`, `drop_table`, `query_table`.
- `DataStoreImplementations` = `Annotated[Union[SQLiteDataStore], Field(discriminator="implementation")]`; `_IMPLEMENTATION_ADAPTER` TypeAdapter.
- `DataStoreImplementationColumn(TypeDecorator)` — JSON column that serializes/parses implementations at the DB boundary.
- `DataStore` (SQLModel table): name PK, implementation, description, creation_date.

### Authorization vocabulary — `app/src/authz/policy.py`
- `ResourceScope(StrEnum)`: SYSTEM, PROJECT.
- `ResourceType(StrEnum)`: PROJECT, DATASTORE, TABLE, USER; property `.scope` reads `_SCOPES`.
- `_SCOPES` — module-level map; import-time check raises `ConfigurationError` for any unscoped type.
- `Action(StrEnum)`: `project.read/update/delete/manage_members`, `datastore.create/read/query/update/delete`, `table.create/read/query/write/delete`, `user.create/read/issue_key`.
- `Subject` (id, email, is_platform_admin, project_roles: dict[UUID, ProjectRole]).
- `Resource` (type, id: str|None, project_id: UUID|None) + `scope` computed field.
- `AuthorizationRequest` (subject, action, resource); `Decision` (allow, reason).
- Protocols: `PolicyDecisionPoint.decide()`, `ResourceFilter.filter_allowed()`.

### Implementations / runtime objects
- `OpaPolicyDecisionPoint` — `app/src/authz/opa.py` (implements both protocols; POSTs `/v1/data/<path>`).
- `AccessEnforcer` — `app/src/authz/enforcement.py` (`ensure_allowed`, `is_allowed`, `keep_allowed`).
- `api_key_scheme` (`HTTPBearer(auto_error=False)`), `CurrentUser`, `CurrentSubject` — `app/src/auth/dependencies.py`.
- `IssuedApiKey` (record + secret) — `app/src/services/api_keys.py`.
- `ApplicationServices` (frozen dataclass: config, engine, enforcer) — `app/src/state.py`.
- Exceptions — `app/src/exceptions.py`: `DataPlatformError` base; `ConfigurationError`, `SchemaMigrationError`, `ObjectNotFoundError`, `DuplicateObjectError`, `AuthenticationError` -> `InvalidApiKeyError`, `AuthorizationError` -> `PolicyDecisionPointError` / `PermissionDeniedError`, `StorageError` -> `UnsuitableDataStoreError` / `TableProvisioningError` / `QueryRefusedError` / `QueryFailedError`.
- Request/response models:
  - `src/endpoints/users.py`: `CurrentUserResponse`, `UserResponse`, `CreateUserRequest`, `CreateApiKeyRequest`, `ApiKeyResponse`, `IssuedApiKeyResponse`, `CreatedUserResponse`.
  - `src/endpoints/tables.py`: `CreateTableRequest`, `TableQueryRequest`.
  - `src/endpoints/projects.py`: `CreateProjectRequest`, `GrantMembershipRequest`, `ProjectMembershipResponse`.
  - `src/endpoints/datastores.py`: `CreateDataStoreRequest`.
- Test doubles — `ScriptedDecisionPoint`, `BrokenDecisionPoint` (`tests/test_enforcement.py`). There is no identity stub any more.

## Functions

| Function | Path |
|---|---|
| `main()`, module-level `app` | `app/main.py` |
| `create_app(*, config)`, inner `lifespan`, `GET /` handler `default()` | `app/src/app.py` |
| `load_config(*, path)`, `AuthConfig._check_admins_are_distinct` | `app/src/config.py` |
| `configuration_path()`, `load_configuration()` | `app/src/environment.py` |
| `create_database_engine(*, config)`, `open_session(*, engine)` | `app/src/db.py` |
| `upgrade_to_head(*, engine)`, `_alembic_configuration`, `_predates_alembic`; constants `BASELINE_REVISION`, `_BASELINE_TABLES` | `app/src/schema.py` |
| `_database_url()`, `_run(*, connection)`, `run_migrations_offline()`, `run_migrations_online()` | `app/migrations/env.py` |
| `upgrade()`, `downgrade()` | each file in `app/migrations/versions/` |
| `get_services`, `get_session`, `get_enforcer`, `get_configuration`; aliases `Services`, `DatabaseSession`, `Enforcer`, `Configuration` | `app/src/dependencies.py` |
| `generate_key()`, `digest_of(*, key)`; `KEY_PREFIX = "dpk_"` | `app/src/auth/api_keys.py` |
| `current_user(credentials, session)`, `current_subject(user, session)` | `app/src/auth/dependencies.py` |
| `issue_api_key`, `authenticate`, `_is_usable`, `list_api_keys`, `revoke_api_key` | `app/src/services/api_keys.py` |
| `ensure_bootstrap_admins`, `_ensure_administrator`, `_ensure_key`, `_ensure_key_is_still_theirs`; `BOOTSTRAP_KEY_NAME = "bootstrap"` | `app/src/services/bootstrap.py` |
| `OpaPolicyDecisionPoint.decide/filter_allowed/_query/check_reachable` | `app/src/authz/opa.py` |
| `AccessEnforcer.ensure_allowed/is_allowed/keep_allowed` | `app/src/authz/enforcement.py` |
| `create_user`, `get_user`, `find_user_by_email`, `list_users`, `describe_subject` | `app/src/services/users.py` |
| `create_project`, `get_project`, `list_projects`, `roles_of_user`, `set_member_role`, `list_members` | `app/src/services/projects.py` |
| `namespace_of(*, project_id)` (-> `p<uuid.hex>`), `_storage_behind`, `get_table`, `list_tables`, `create_table`, `delete_table`, `run_query` | `app/src/services/tables.py` |
| `create_datastore`, `get_datastore`, `list_datastores`, `delete_datastore`, `run_query` | `app/src/services/datastores.py` |
| `create_users_router()`; routes `GET /users/me`, `POST/GET /users/me/api-keys`, `DELETE /users/me/api-keys/{key_id}`, `POST /users/`, `GET /users/`, `POST /users/{user_id}/api-keys`; helpers `_as_resource`, `_describe_key`, `_describe_issued_key`, `_describe_user` | `app/src/endpoints/users.py` |
| `create_projects_router()`; routes `POST /projects/`, `GET /projects/`, `GET /projects/{id}`, `GET /projects/{id}/members`, `PUT /projects/{id}/members`; helper `_as_resource(*, project)` | `app/src/endpoints/projects.py` |
| `create_tables_router()` (prefix `/projects/{project_id}/tables`); routes `POST /`, `GET /`, `GET /{table_name}`, `POST /{table_name}/query`, `DELETE /{table_name}`; helper `_as_resource(*, project_id, identifier)` | `app/src/endpoints/tables.py` |
| `create_datastores_router()`; routes `GET /datastores/query`, `POST /datastores/`, `GET /datastores/`, `GET /datastores/{datastore_name}`, `DELETE /datastores/{datastore_name}`; helper `_as_resource(*, name)` | `app/src/endpoints/datastores.py` |
| `register_error_handlers(*, app)`: InvalidApiKey->401(+WWW-Authenticate), PermissionDenied->403(+action/resource/reason), PolicyDecisionPointError->503, ObjectNotFound->404, DuplicateObject->409, QueryRefused->403, QueryFailed->400, UnsuitableDataStore->400, TableProvisioning->400 | `app/src/endpoints/errors.py` |
| `build_authorizer`, inner `authorize`, `is_refusal` | `app/src/sqlite_privileges.py` |
| `validate_identifier` | `app/src/storage.py` |
| Rego rules: `viewer/editor/admin/owner_permissions`, `role_permissions`, `default allow := false`, `allow`, `decision`, `reason` (3 variants keyed on scope), `allowed_resource_ids`, `is_allowed` (platform-admin rule + project-role rule), `project_role` | `app/policies/dataplatform/authz.rego` |
| Fixtures/helpers: `api_key_for`, `_free_port`, `opa_url` (session-scoped real OPA server, skips if `opa` not on PATH), `config`, `engine` (**migrates to head**), `session`, `callers` (alice/bob/root, each with a derived key), `client`, `headers_for`, `user_id_of`, `make_platform_admin` | `app/tests/conftest.py` |

### Test suites
- `tests/test_api_keys.py` (~35 tests) — key generation/uniqueness/prefix, authentication, missing/unknown/revoked/expired keys, self-service key issue/list/revoke, admin-only user creation and key issuance, digest-only storage, bootstrap admin creation/rotation/refusals.
- `tests/test_table_access.py` (~16 tests) — end-to-end table lifecycle through HTTP: owner creates, viewer reads but cannot write, editor writes and alters but cannot create/delete, outsiders reach nothing, platform admins reach everything, cross-project isolation, DDL refused even for owners, delete destroys data, listings scoped per project.
- `tests/test_table_storage.py` (~20 tests) — the SQLite privilege boundary against a real database: read-only vs read-write, ALTER, refusal of CREATE/DROP/ATTACH, sibling tables in the same namespace refused, other namespaces simply absent, second-statement smuggling, schema hidden from read-only, column type/name validation. Runs without OPA.
- `tests/test_datastore_access.py` — admin-only datastore lifecycle; regular users refused; listing empty; a refusal does not reveal existence.
- `tests/test_project_access.py` — anyone may create; invisible to outsiders; membership opens access; viewer cannot manage members; platform admins reach every project.
- `tests/test_migrations.py` — migrations vs. models agree (`compare_metadata`), pre-Alembic DB carried forward, rows survive, re-running is a no-op, fresh DB at head, every model table exists.
- `tests/test_enforcement.py` — allow/deny/broken decision point behaviour.
- `tests/test_opa_client.py` — result parsing, input shape, unreachable/unloaded/erroring/nonsense answers all fail closed, empty-list short circuit.
- `policies/dataplatform/authz_test.rego` (~29 tests) — datastores, projects, tables, users, filtering, and each denial reason.

## Dependencies

Runtime (from `app/pyproject.toml`):
- **alembic** (>=1.19.1) — schema migrations, driven from the CLI and from `src/schema.py` at startup.
- **fastapi** (>=0.136.3) — routing, DI, OpenAPI, `HTTPBearer` security scheme.
- **pydantic** (>=2.13.4) — config schema, authz vocabulary, discriminated implementation union, computed `scope`, column/identifier validation.
- **sqlmodel** (>=0.0.38) + SQLAlchemy — metadata store models, engine, sessions, custom `TypeDecorator`.
- **httpx** (>=0.28.1) — async client for the OPA client (and used directly in tests).
- **loguru** (>=0.7.3) — logging.
- **pyyaml** (>=6.0.3) — configuration file parsing.
- **email-validator** (>=2.3.0) — `EmailStr` in config and request bodies.
- stdlib `sqlite3` — the only shipped datastore implementation, including its authorizer API.
- stdlib `secrets` / `hashlib` — API key generation and digesting.

Dev group: `fastapi[standard]` (uvicorn, `fastapi dev`), `pytest` (>=9.1.1), `pytest-asyncio` (>=1.4.0, auto mode), `ty` (type checker). Managed with **uv** (`uv.lock`).

External services / tooling:
- **Open Policy Agent** server (docker image `openpolicyagent/opa:1.19.0`, or a local `opa` binary) at `opa.url`, serving `dataplatform/authz/decision` and `dataplatform/authz/allowed_resource_ids`. Required at runtime — without it the API returns 503 for everything guarded.
- **Database**: any SQLAlchemy URL; SQLite by default (`sqlite:///mydb.db`).
- **Helm/Kubernetes**: `chart/` depends on the Apache Ozone Helm chart (object storage); OPA is expected to run as a sidecar with the policy from a ConfigMap.
- `opa` binary on PATH for `opa test policies -v` and for the Python tests that boot a real OPA (they skip otherwise).
- No external identity provider any more — the platform issues its own credentials.

## Notable design notes / gotchas

- `src/app.py` is the only module naming OPA; everything else depends on `PolicyDecisionPoint` / `ResourceFilter`. Authentication has no such seam by design.
- `Resource.scope` is computed from the type, never supplied — that is what stops a caller describing a system object as a project one.
- `POST /projects/` performs **no** enforcer call: any authenticated user may create a project and becomes its `owner` member.
- The three `/users/me/...` key endpoints are deliberately **not** put to the policy; everything about other people is.
- Datastore and user endpoints ask the policy **before** the database, so a refusal cannot reveal whether a name exists. Project/table endpoints fetch first, so a missing object is a 404.
- `GET /datastores/query` is declared before `/{datastore_name}`, so the literal path wins.
- `POST /projects/{id}/tables/{name}/query` is the only place `AccessEnforcer.is_allowed` is used: `table.write` is asked first and, if refused, `table.query` is *enforced*; the answer picks `QueryPrivilege`. A decision-point failure still raises rather than downgrading.
- Table creation provisions storage first then records it (rolling back the storage on failure); deletion drops storage first then forgets the record.
- A namespace is `p<project_uuid.hex>`, derived not stored; for SQLite it becomes a sibling database file `<stem>__<namespace><suffix>`.
- Known, documented limitation: a read-write SQLite caller can read `sqlite_master` within their own namespace, because `ALTER TABLE` requires it. `SQLITE_ALTER_TABLE` passes the table as its *second* argument — reading the first would permit altering any table.
- Bootstrap: `ensure_bootstrap_admins` runs on every start; changing the configured key rotates it (old one revoked), while re-using a revoked or somebody else's key raises `ConfigurationError` and stops the process.
- Autogenerated revisions render the implementation column as `src.datastore.DataStoreImplementationColumn()` — the README requires replacing it with `sa.JSON()`, since revisions must never import from `src`.
- `render_as_batch=True` is on for SQLite; migrations run inside `engine.begin()` and `env.py` reuses a borrowed `config.attributes["connection"]`.
- Pre-Alembic databases are detected by the presence of any of `user/project/projectmember/datastore/catalog` with no `alembic_version` table, then stamped `0001_baseline`.
