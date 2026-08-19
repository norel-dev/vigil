# DataPlatform API

An API for managing a dataplatform, with the following goals:
1. Abstracting the management of storing and retriving data from multiple underlying stores
2. Indexing of entities extracted through data being input into the platform
3. Management of LLM Agents whose goal is to conduct research on data on the platform

## Access control

Callers authenticate with an **API key**. What they may then do is decided by an
[Open Policy Agent](https://www.openpolicyagent.org/) policy that lives in
[`policies/`](policies/), not by the API: every request is turned into a
question, and OPA answers it.

The platform has **two levels**, and every object states which one it belongs to.
That scope is what decides which rules apply to it:

| Scope     | What lives there | Who may act on it |
|-----------|------------------|-------------------|
| `system`  | **datastores** — the storage the whole platform is built on — and **users** | platform administrators, and nobody else |
| `project` | **projects**, and the **tables** and **blobs** that sit under them | whoever holds a role in the owning project |

Datastores are infrastructure: registering one adds hardware the platform runs
on, so it is not something a user does inside their own space. A user who owns
a project still gets a `403`, with the policy's own explanation, when they try
to read or query one. Users are the platform's own record of who exists, so
they sit at the same level. Projects are the opposite — any user may create
one and becomes its `owner`.

There is one thing about a datastore that is not the platform's alone, and it
has an endpoint of its own. A project has to *name* a datastore to put a table
or a blob in it, so **`GET /datastores/catalogue`** answers every authenticated
caller with what storage exists and what each kind holds:

```http
GET /datastores/catalogue?data_type=blob

[
  {"name": "objects",    "data_type": "blob", "description": "fast, local"},
  {"name": "cold-store", "data_type": "blob", "description": "archival, cheap"}
]
```

That is the whole of it: a name, a data type and a description. There is no
endpoint in it, no credential, and no way to reach the storage — an entry is
built field by field into a model of its own rather than derived from the
datastore, so an implementation that grows a new credential field tomorrow
cannot leak it here. Knowing a name also opens nothing: reading, querying and
removing the datastore behind it still answer a regular user with `403`.

The cost is stated plainly, because it is real: every authenticated caller can
now learn that a public datastore by some name exists and read its description,
where before only administrators could. Name datastores accordingly. The
alternative was a choice the platform offers that nobody outside the
administrators could discover how to make.

### Datastores that are not on the list

A datastore is registered as `public` or `private`, and that decides one thing:
whether it appears in the catalogue. This is how an administrator points the
platform at storage meant for their own use without every user reading its name.

```http
POST  /datastores/            {"name": "scratch", "visibility": "private", ...}
PATCH /datastores/scratch     {"visibility": "public"}     # offer it after all
```

`visibility` defaults to `public`, because registering storage is normally an
offer to build on it, and every datastore registered before this existed is
public for the same reason. `GET /datastores/` — the administrator's view — shows
every datastore whatever its visibility, since one that could not be found could
not be managed.

**A private datastore is hidden, not protected.** Nothing in the policy consults
`visibility`: a user who is told the name can put a table or a blob in a private
datastore exactly as they could a public one, and everything that was already
inside one goes on working when it is withdrawn. What keeps it hidden is only
that nothing else prints the name. Use it to keep a list short and to avoid
offering storage that is not meant for general use — never as the thing standing
between a user and storage they must not reach.

A project reaches the data behind a datastore through an object of its own — a
**table** when the data has a shape, a **blob** when it does not — never through
the datastore. The roles are what govern them:

| Role     | May do                                                                       |
|----------|------------------------------------------------------------------------------|
| `viewer` | read the project, see its tables and blobs, run read-only SQL, download blobs |
| `editor` | the above, plus write rows, alter a table's shape, and upload to blobs        |
| `admin`  | the above, plus update the project and manage its members                     |
| `owner`  | the above, plus delete the project, and create and delete tables and blobs    |

The administrators listed under `auth.bootstrap_platform_admins` in the
configuration exist as soon as the platform starts, each already holding the key
the configuration gave them. They are trusted everywhere: at the project level
they bypass membership, and at the system level they are the only way in at all.
Since every user and every key is created by an administrator, an empty list
leaves a platform nobody can reach.

Three properties are worth calling out:

* **The API fails closed.** If OPA is unreachable, or its policy is not loaded,
  requests are answered with `503` and nothing happens. There is no code path
  that treats an absent decision as permission.
* **Listings are filtered by the same policy**, in a single round trip, rather
  than by a second implementation of the rules in Python. A regular user's
  `GET /datastores/` is an empty list, not a refusal.
* **A refusal reveals nothing.** Because a datastore's scope is enough to decide
  the question, the policy is consulted before the database is, so a caller who
  may not see datastores gets the same `403` whether or not the name exists. A
  key that is missing, unknown, revoked or expired is answered identically for
  the same reason. The catalogue above is the deliberate exception, and it is
  an exception to what is *listed*, not to what is *allowed*: it hands out
  names, and no endpoint behind those names treats its readers any differently.

## Tables

A table is a structured, SQL table that a project owns, living inside a
datastore whose data type is `table`. Creating one is how a project claims
storage:

```http
POST /projects/{project_id}/tables/
{
  "name": "customers",
  "datastore": "warehouse",
  "columns": [
    {"name": "id",   "type": "INTEGER",      "nullable": false},
    {"name": "email", "type": "VARCHAR(255)"}
  ]
}
```

and querying it is how the project uses it:

```http
POST /projects/{project_id}/tables/customers/query
{"query": "INSERT INTO customers VALUES (1, 'someone@example.com')"}
```

Column types are written in the datastore's own dialect and are passed to the
engine as given — the platform does not try to understand them. It only checks
that the text cannot stop being a type, and that column and table names are
plain identifiers, because all three are placed into a `CREATE TABLE` that runs
at the platform's own privilege.

### How the limits are enforced

A caller may run DDL and DML against their table, but **may not create or drop
anything, and may not reach another table**. Neither rule is enforced by reading
the SQL. The platform never parses, classifies or rewrites a statement, because
anything that did would have to be right about every way of phrasing a query.
Instead there are three privilege levels, and the engine enforces them:

| Privilege     | Used for                       | May do                              |
|---------------|--------------------------------|-------------------------------------|
| provisioning  | creating and dropping tables   | everything — never given to a caller |
| read-write    | a caller granted `table.write` | select, insert, update, delete, alter — on one table |
| read-only     | a caller granted `table.query` | select — on one table                |

The caller's role decides which of the two lower levels the platform connects
with, and from that point the database refuses the rest. `CREATE` and `DROP`
stay with the platform so that its record of what exists cannot drift from what
is really in the datastore — which is also why deleting a table through the API
destroys the data, rather than only forgetting it the way deleting a datastore
does.

Each project's tables live in a **namespace** of their own inside the datastore,
so a name only has to be unique within its project. Two projects may both have a
table called `customers`, and each writes `SELECT * FROM customers` to reach
their own.

### What this means for SQLite

SQLite has no users, roles or `GRANT`, so the privilege levels are realised with
its [authorization callback](https://sqlite.org/c3ref/set_authorizer.html),
which SQLite consults while *compiling* each statement and which is therefore a
real boundary rather than a filter over text. It holds against joins, subqueries
and common table expressions alike. A namespace becomes a database file of its
own, named after the configured one, so `/data/warehouse.db` grows siblings like
`/data/warehouse__p3f2a....db`.

One limitation is worth stating plainly: **a read-write caller can read
`sqlite_master`**, and so can see the definitions of the other tables in their
own project's namespace. This is not a choice — `ALTER TABLE` makes SQLite read
that catalogue on the caller's behalf, so refusing it would break `ALTER`. No
rows are exposed, only definitions, and only within the caller's own namespace;
read-only callers get no access to it at all. The rules, and the two SQLite
quirks behind them, are documented in `src/features/datastores/implementations/_sqlite_privileges.py`.

## Blobs

A blob is an unstructured object that a project owns — a file, a model, a
parquet dump — living inside a datastore whose data type is `blob`. Blobs are
what a project holds when the data has no shape the platform knows.

**Blobs have no hierarchy.** A key may read like a path, but there is nothing to
create before using it:

```http
POST /projects/{project_id}/blobs/
{
  "key": "reports/2026/q1.parquet",
  "datastore": "objects",
  "content_type": "application/octet-stream"
}
```

`reports/2026/q1.parquet` is one blob with one name. The slashes matter only to
whoever reads the name, and to `GET /projects/{id}/blobs/?prefix=reports/`.

### Choosing where a blob goes

`datastore` is the choice, and it is made **per blob, when the blob is
created**. A platform usually holds more than one place to put bytes — fast
and local beside slow and cheap, one region beside another — and nothing says
a project's blobs all belong in the same one:

```http
POST /projects/{project_id}/blobs/   {"key": "model.pkl",   "datastore": "objects"}
POST /projects/{project_id}/blobs/   {"key": "2019.tar.gz", "datastore": "cold-store"}
```

Ask `GET /datastores/catalogue?data_type=blob` for the names to choose from.

The choice is binding rather than advisory. It is recorded on the blob, it
comes back on every read and every listing as `datastore_name`, and it is what
every later operation follows: the upload URL is signed by the store that was
chosen, and so are downloads, so is the size a read reports, and so is a
delete. Two things follow from it being fixed at creation:

* **A key is unique within a project, not within a datastore.** One project
  cannot hold `model.pkl` in two datastores at once; two projects can each hold
  one, in the same datastore or in different ones.
* **A blob does not move.** There is no endpoint that changes which datastore a
  blob lives in, because doing so would mean copying bytes the platform has
  made a point of never carrying. Create the blob you want in the store you
  want, and delete the one you do not.

The store has to be able to hold what is being asked of it, and three ways of
getting that wrong are answered differently: a datastore that holds tables is a
`400`, a name that names nothing is a `404`, and a store that cannot be reached
at all is a `502` — the platform is not broken, the storage somebody chose did
not answer.

### The platform never carries the bytes

Creating a blob writes no data. What comes back is the record **and a URL to
upload through**:

```json
{
  "blob": { "id": "...", "key": "reports/2026/q1.parquet", ... },
  "upload": {
    "url": "http://minio:9000/p3f2a.../reports/2026/q1.parquet?X-Amz-Signature=...",
    "method": "PUT",
    "expires_at": "2026-08-17T12:15:00Z"
  }
}
```

Ask for one later — to download, or to upload again — through the access
endpoint, which is where the caller says what they mean to do:

```http
POST /projects/{project_id}/blobs/{key}/access
{ "operation": "download" }
```

Between creating a blob and uploading to it, the record exists and the store
holds nothing. That is a normal state, and `GET .../blobs/{key}` reports it
plainly: `stored` is `null` until something has been written.

### How the limits are enforced

Nothing here reads a request to decide whether to allow it, which is the same
bargain tables make and the reason both work:

| Role | May |
|---|---|
| viewer | `blob.read`, `blob.download` |
| editor | + `blob.upload` |
| owner | + `blob.create`, `blob.delete` |

The role decides which URL the caller is handed, and the **signature is the
whole of the permission** from there on. It covers the HTTP method, the bucket
and the key together, so a download URL cannot be turned into an upload, and a
URL for one blob cannot be pointed at another — MinIO refuses both, without the
API seeing the attempt.

Two consequences follow, and both are deliberate:

* **A signed URL cannot be withdrawn.** Nothing revokes one early, so they are
  signed for 15 minutes rather than days. A datastore configured with a shorter
  `presigned_url_expiry_seconds` wins; the shorter of the two always does.
* **Deleting goes through the API**, not through a signed URL, because a blob's
  data and the platform's record of it have to go together.

Each project's blobs live in a **namespace** of their own — with MinIO, a bucket
named after the project — so a key only has to be unique within its project. Two
projects may both hold `model.pkl`, and neither can reach the other's.

### Registering a MinIO

```http
POST /datastores/
{
  "name": "objects",
  "visibility": "public",
  "datastore": {
    "implementation": "minio",
    "endpoint": "localhost:9000",
    "access_key": "dataplatform",
    "secret_key": "dataplatform-secret",
    "secure": false,
    "presigned_url_expiry_seconds": 900
  }
}
```

The credential is the platform's own and is never handed to a caller. It is
stored with the datastore, because the platform has to reconnect with it, but it
is **redacted from every API response** — reading the datastore back shows
`"secret_key": "**********"`.

That holds on two different paths, and it takes both. `secret_key` is a
`SecretStr`, so it does not appear in a `repr`, a log line, or an exception that
interpolates the datastore — which is how a credential usually escapes. A
`SecretStr` masks itself when serialized too, though, which would mean storing
the mask and never reconnecting, so a field serializer reveals it for exactly
one destination: the dump in `src/features/datastores/model.py` that writes the database row.
Every other dump, the API's responses included, gets the mask.

Anything speaking S3 works here; `secure: false` is for local development only.

## Running it

### 1. Start Open Policy Agent and MinIO

```bash
docker compose up -d opa minio
```

MinIO is only needed if you mean to use blobs. Its console is at
`http://localhost:9001`.

Or, with OPA installed locally:

```bash
opa run --server --addr localhost:8181 policies/
```

### 2. Configure the way in

```bash
cp config.example.yaml config.yaml
python -c "import secrets; print('dpk_' + secrets.token_urlsafe(32))"
```

Put that key under `auth.bootstrap_platform_admins` in `config.yaml`, together
with the address and name the administrator holding it should have. `config.yaml`
is not committed, because that key is a secret in the same sense a password is.

### 3. Run it

```bash
uv run fastapi dev main.py
```

`DATAPLATFORM_CONFIG` names the configuration file to load, and defaults to
`./config.yaml`. It is the only environment variable the process reads.

Open http://localhost:8000/docs, press **Authorize**, and paste the key. Every
request carries it as `Authorization: Bearer <key>`:

```bash
curl -H "Authorization: Bearer dpk_..." http://localhost:8000/users/me
```

Then, to see the model work end to end: as the bootstrap administrator,
`POST /datastores/` to register the platform's storage and `POST /users/` to
create somebody else — that call answers with their first key, once. Call the
same two endpoints as them and watch both come back `403`. `POST /projects/` and
`PUT /projects/{id}/members` are the other half: any user may create a project
and let somebody else into it.

As them, `GET /datastores/catalogue` shows what storage they may choose from —
the one thing about a datastore a regular user may read, and the reason the
next two calls have a name to put in.

Then create a table in that project with `POST /projects/{id}/tables/`, insert a
row through its `/query` endpoint, and invite somebody as a `viewer` to watch the
same insert come back `403` while a `SELECT` still works.

## API keys

A key is 256 bits from `secrets.token_urlsafe`, handed over once and never
stored: the platform keeps a SHA-256 digest of it, and a presented key is
recognised by looking that digest up. A copy of the `apikey` table is therefore
of no use to whoever takes it, and a lost key cannot be recovered — only
replaced. Digesting is enough, and a password hash would not be: a key is
randomness this platform generated, not something a person chose.

| Call | Who | What it does |
|------|-----|--------------|
| `POST /users/me/api-keys` | anybody | issue yourself another key |
| `GET /users/me/api-keys` | anybody | list your keys, revoked ones included |
| `DELETE /users/me/api-keys/{id}` | anybody | withdraw one of your keys |
| `POST /users/` | platform admins | create a user, and their first key |
| `GET /users/` | platform admins | list who exists |
| `POST /users/{id}/api-keys` | platform admins | issue a key to somebody who lost theirs |

The first three act on the caller and are not put to the policy: authentication
has already established whose account the request is about, so there is no
access question left to ask. The rest are about other people, and go through the
policy as system scoped resources like any datastore.

**Rotating a key** is creating the next one, moving over to it, and revoking the
old one. Revoking keeps the row and records when it stopped being accepted, so
what once existed stays answerable. **Rotating the bootstrap key** is changing it
in `config.yaml` and restarting: the key it replaces is revoked on the way.

## Database migrations

The schema is owned by the [Alembic](https://alembic.sqlalchemy.org/) revisions
under `migrations/versions/`, not by the models. **The API brings its database
up to head as it starts**, so a database that is behind is upgraded rather than
left to fail on the first query that touches a missing column.

Alembic reads the same `config.yaml` the API does, through `src/platform/environment.py`,
so there is no second copy of the database URL and no way to migrate a different
database than the one you are serving. `DATAPLATFORM_CONFIG` selects the file
here too.

After changing a model:

```bash
uv run alembic revision --autogenerate -m "what changed"   # write the revision
uv run alembic upgrade head                                # apply it
```

Read the generated revision before committing it. Two things need a human:

* autogenerate renders the datastore's `implementation` column as
  `src.datastore.DataStoreImplementationColumn()`. Replace that with `sa.JSON()`.
  A revision is a historical record and has to keep running after the class it
  was named for has changed or gone, so revisions never import from `src`.
* SQLite cannot alter a column in place. `render_as_batch` is on, so Alembic
  rebuilds the table around the change; check that what it produced is what you
  meant.

Other useful commands:

```bash
uv run alembic current              # which revision this database is at
uv run alembic history              # every revision, newest first
uv run alembic downgrade -1         # step back one revision
uv run alembic check                # does the schema still match the models?
```

Databases created before Alembic was introduced carry no revision. They are
recognised on the first start, recorded as `0001_baseline` — the schema
`SQLModel.metadata.create_all` used to produce — and then upgraded like any
other. Nothing has to be deleted by hand.

## Tests

```bash
uv run pytest            # API tests, including a real OPA when it is installed
opa test policies -v     # the policy's own tests
uv run ruff check .      # lint and import order
uv run ty check          # types
uv run pytest --cov      # the same tests, with the coverage gate applied
```

Coverage is asked for rather than always on, because the gate is about the
suite as a whole: running one file with `--cov` measures all of `src` against
the handful of tests in it and fails for the wrong reason. Run it over the
whole suite, where it fails below 80%. The suite sits far above that; the floor
is there so that a change which quietly stops testing something fails rather
than merely reporting a smaller number nobody reads.

`ruff` is configured in `pyproject.toml`. The security rules (`S`) are the
reason the list is worth having: `src/` raises none of them today, so the rule
is a ratchet rather than a cleanup. Tests are exempted from the handful that
only make sense about production code — a test asserts, and builds SQL out of
the very identifiers it is checking the handling of.

Every test runs against a database built by the migrations rather than from the
models, and `tests/test_migrations.py` fails the suite if the two ever disagree
— which is what stops a model change from being merged without a revision.

The API tests start an `opa` server themselves and run the real policy against
the real routers, authenticating with real API keys, so they check what the
platform will actually allow rather than what a stub was told to say. Nothing in
the request path is replaced; what the fixtures arrange is only the users
themselves, written straight into the database with a key derived from each
caller's name. They skip if the `opa` binary is not on `PATH`; the policy is then
still covered by `opa test`.

The blob tests hold to the same standard, and go further: they upload and
download through the signed URLs the API hands out, and check that a download
URL really is refused when used to write. A signed URL is the entire permission
once it leaves the platform, so a test that only checked a URL came back would
be checking that the platform believes it granted something. They need a real
MinIO — a local `minio` binary is used if there is one, Docker otherwise — and
skip when neither is available.

Two of them, in fact. Proving that a blob went to the datastore its project
chose takes a second datastore that the blob is provably *not* in, so the
suite runs two independent MinIO servers and goes to both of them to check.
One server behind two datastores could only ever have shown that the platform
wrote down the right name.

## Layout

The code is grouped by **what the platform offers**, not by which layer a file
belongs to. Everything one feature needs — its record, its service, its
routes, and the storage protocol it demands of a datastore — sits in one
directory, so reading a feature end to end means reading one folder rather
than picking the same filename out of four.

```
main.py                     entry point: loads the config, builds the app
alembic.ini                 migration tool settings (the URL comes from config.yaml)
migrations/                 the schema's history
  env.py                    how Alembic reaches the configured database
  versions/                 one file per revision
src/
  app.py                    wires abstractions to OPA and mounts the routers

  features/                 one package per thing the platform offers
    users/                  the only actor there is
      model.py              the user record
      service.py            creating and finding users
      router.py             user endpoints, and a caller's own API keys
    projects/               the unit of access control
      model.py              the project, and who is a member at which role
      service.py            projects and their membership
      router.py             project endpoints
    tables/                 structured data a project holds
      model.py              the platform's record of a table
      storage.py            TableStorage, and the privilege a query runs at
      service.py            provisioning, resolving and querying tables
      router.py             table endpoints
    blobs/                  unstructured data a project holds
      model.py              the platform's record of a blob
      storage.py            BlobStorage, and what a signed URL is good for
      service.py            recording blobs and signing access to them
      router.py             blob endpoints
    datastores/             the storage the whole platform is built on
      storage.py            the vocabulary every store is described by
      model.py              the datastore record, and the union of implementations
      service.py            reading, writing and querying datastores
      catalogue.py          what storage is on offer, without how to reach it
      router.py             datastore endpoints
      implementations/      one module per concrete store
        base.py             what every implementation offers
        sqlite.py           SQLite, which holds tables
        minio.py            MinIO, which holds blobs
        _sqlite_privileges.py  the rules of a restricted SQLite connection

  identity/                 who the caller is
    keys.py                 what a key is, and what is kept of one
    model.py                the stored key record
    service.py              issuing, using and withdrawing keys
    caller.py               the dependencies that identify a caller
    bootstrap.py            the first administrators, from the configuration
  authz/                    what the caller may do
    policy.py               subjects, actions, resources, scopes, decisions
    opa.py                  the Open Policy Agent client
    enforcement.py          turning decisions into refusals

  database/                 the platform's own database
    engine.py               engine and sessions
    migrations.py           bringing the database up to the latest revision
  platform/                 the plumbing every feature stands on
    config.py               the YAML configuration schema
    environment.py          which config file this process reads
    exceptions.py           the platform's error types
    error_handlers.py       what each error looks like on the wire
    state.py                the components that outlive a request
    dependencies.py         FastAPI dependencies for the shared components
policies/dataplatform/      the Rego policy and its tests
```

Three rules hold this together, and each one is worth keeping.

**A feature owns its storage protocol.** `TableStorage` lives with tables and
`BlobStorage` with blobs, rather than in one shared module, which is what lets
a store that holds blobs decline to have methods about tables at all. What
every store shares — the shape of a statement, its answer, and how a project's
corner of a store is named — is the only thing in
`features/datastores/storage.py`.

**No `__init__.py` re-exports anything.** Features call each other's services
freely (a table resolves its datastore before it is provisioned), and the
import graph stays acyclic only because every import names the module it means.
An `__init__` that re-exported would close a loop the first time two features
needed each other.

**`platform` and `database` know nothing about features.** Configuration,
errors, sessions and migrations are used by everything and depend on nothing,
so a change to a feature can never reach them.

`identity` and `authz` sit between the two and do reach into features, in
exactly two places and for the same reason: a key authenticates a **user**,
and a policy subject carries the **project roles** they hold. So
`identity` imports `features.users` and `authz` imports
`features.projects.model`. Both are the domain being honest rather than a
layering slip — the alternative is a second `User` that has to be kept in step
with the first. Nothing else crosses that way, and nothing else should.

Nothing outside `src/app.py` names OPA: the rest of the code depends on
`PolicyDecisionPoint` and `ResourceFilter`, so replacing the policy engine is a
matter of writing one class and changing the wiring in one place. Authentication
needs no such seam — the platform issues its own credentials, so there is
nothing external to stand behind an interface.
