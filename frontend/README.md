# dataplatform console

A frontend for the DataPlatform API. It does three things:

1. **Blobs** — upload files, and look at them: pictures, video, audio, pdfs,
   and source.
2. **Tables** — create a table, add columns to it, put rows in it.
3. **Workspaces** — switch between projects, create new ones, and say who
   may reach them.

Built on the Vigil design system in `design/`, which is vendored unmodified
into `src/vigil/tokens.css` and `src/vigil/components.css`. `src/vigil/app.css`
is the console's own layer; like `components.css`, it names no colour, size or
duration of its own and only resolves tokens.

## Running it

The API, MinIO and OPA come from the backend's compose stack:

```bash
cd ../backend && docker compose up -d
```

Then:

```bash
npm install
npm run dev          # http://localhost:5173
```

Sign in with an API key. Running the compose stack locally, the bootstrap
administrator's key is in `../backend/config.docker.yaml`.

## Two proxies, and why they exist

`vite.config.ts` proxies both of the console's upstreams, because the browser
is a third party neither of them was built for.

**`/api` → `localhost:8000`.** The API sets no CORS headers — it expects to be
called by something holding a key, not by a page — so the console talks to it
same-origin and lets the dev server cross the boundary.

**`/blob` → `localhost:9000`.** The API signs upload and download URLs against
the hostname it knows the object store by, which is `minio:9000` on the compose
network and unreachable from a laptop. The AWS signature covers the `Host`
header, so the URL cannot simply be rewritten to `localhost`: the request has
to go to localhost while still claiming to be addressed to `minio:9000`. The
proxy sets that header on the outgoing request options rather than in a
`proxyReq` handler — a request carrying `Expect: 100-continue` has already
flushed its headers by the time that event fires, which would break uploads
over about a megabyte and nothing else.

For a real deployment neither proxy is the answer: give the API a CORS policy,
and configure the MinIO datastore with the endpoint clients actually reach.

## What the console assumes about the API

- **Auth** is `Authorization: Bearer <key>`, and what the key may do is decided
  by OPA from the caller's project roles. The console asks `/users/me` on sign
  in and reads roles from there; it does not try to predict a decision, so a
  refusal is shown as the platform worded it.
- **A table's shape** is read with `SELECT * FROM <table> LIMIT 0` and taken
  from `metadata.columns`. `PRAGMA` is refused by the privilege the query
  endpoint connects with, which is correct and not worth working around.
- **Adding a column and inserting a row** are ordinary statements through the
  query endpoint. Both forms print the SQL they composed before running it —
  see below.
- **A primary key is asked for by marking columns**, one at a time, in `create
  table`. Every marked column forms one key together in the order shown, so one
  mark makes a single-column key and several make a composite one. Marking a
  column also makes it `not null` and disables that toggle, because the
  platform refuses a key column that may hold no value; the contradiction is
  not composable here, so it never has to be explained. `create table` is the
  only place the mark appears — a key cannot be added by an `ALTER`, which is
  why `add column` has no such toggle.
- **Uploading** is two steps, and the dialog lists both before either runs:
  record the blob, then PUT the bytes to the signed URL that comes back.
- **A blob's record and its bytes** are separate facts. `stored: null` means
  recorded but never filled, which the console renders as a dashed frame rather
  than as a broken image.
- **A blob's type** is asked for twice and the two answers can differ. The
  declared type is whatever the project said when it recorded the blob; the
  stored type is what the object store reports. The console picks a viewer on
  the stored one, falling back to the declared one only when there are no
  bytes yet, because the stored type is what the browser will act on when it
  fetches the signed URL.

## The one loud idea

No form changes a table without printing the statement it composed. `add
column` shows its `ALTER TABLE`; `insert row` shows its `INSERT`, updating as
you type; `create table` shows a sketch of the shape being asked for, labelled
as a sketch because the platform writes the real statement itself. The reason
is that the platform does not read the statement either — the database engine
accepts or refuses it — so a reader who never saw the text cannot understand
the refusal when it comes.

## Keyboard

One dispatcher owns every key, and the command line and the palette read one
registry, so they cannot disagree about what exists.

| Key | |
| --- | --- |
| `1`–`9` | jump to buffer *n* |
| `j` / `k` | move the rail cursor |
| `↵` | open the row under the cursor in this tab, or fold the branch under it |
| `⇧↵` | open the row under the cursor in a new tab |
| `:` | command line |
| `/` or `f` | find a blob by key |
| `⌘K` / `Ctrl+K` | command palette |
| `⌘↵` | run the statement in the well |
| `esc` | dismiss |

`:new tab` duplicates the buffer you are in and `:close` closes it. `:members`
opens the members page and `:grant access` gives somebody a role. `:density`
switches comfortable and compact. `:gloss` hides the line under every section
title. `:forget key` signs out.

## Buffers and workspaces

A tab is one open object — a table, a blob, or one of a workspace's own pages
— the way a buffer in an editor is one open file. It is also a place you put yourself, the
way a browser tab is, and the console treats it as yours:

* **Clicking a table or a blob shows it in the tab you are in.** It never mints
  a tab, and it never sends you off to some other tab that happens to hold the
  same thing. Wherever you were looking is where the next thing appears.
* **A tab is only ever born by being asked for** — `+` on the tabline, `:new
  tab`, `⌘`- or middle-clicking a row in the rail, or `⇧↵` on the rail cursor.
  `+` and `:new tab` hand you a second copy of where you are; the rail's
  modifier-click opens the row you picked. Either way the new tab lands beside
  the one you opened it from rather than at the end.
* **The same object may sit in two tabs at once**, which is the point: open a
  second tab and take one of the two somewhere else, and you can read them
  side by side by flicking between `1`–`9`.

Deleting a table or a blob does not close anything. Every tab that was pointing
at it falls back to that workspace's overview, including tabs other than the one
you deleted from — a tab is yours, and a delete is no reason to take it away.

Which workspace you are in is a property of each buffer rather than of the
window, so **two tabs can sit in two different workspaces at once**. That is why
the workspace is not itself a tab: it lives in the statusline, left of the
context, and clicking it switches the buffer in front of you. Workspace data is
cached per workspace, so tabs across several of them do not re-read each
other's.

## The workspace's pages

A workspace has two pages of its own, and the rail lists them above its
contents. **Overview** is what the workspace holds — its tables and its blobs.
**Members** is who may reach it, and how far.

They are two pages rather than two halves of one because they change for
different reasons and at different people's hands: the inventory moves as work
is done, and the membership moves when access is granted or taken back. The
overview still counts the members in its band, and that count is the way to
the page.

Each is a buffer like any other, so a members page can sit in its own tab
beside a table — which is the point when you are checking a grant against what
somebody would be able to reach.

## Viewers

A blob is bytes and a name, and what to do with them is one decision the
console makes in one place. Each format is a module under `src/viewers/` that
states for itself which content types and which extensions it draws; the
registry asks them in order and returns the first that claims the blob. Adding
a format is adding a file and a line in `registry.ts` — no pane that already
draws six formats correctly has to be opened to make it draw a seventh.

| | drawn with |
| --- | --- |
| image | `<img>` |
| video | `<video>`, and the console's own transport |
| audio | the same transport, with no picture above it |
| pdf | a frame, and the browser's own reader inside it |
| html · markdown · text | printed as source |
| anything else | its size and its type, said plainly |

Resolution asks the **stored content type first and the key second**, in that
order and never mixed. The type is what the browser will act on; the name is a
guess, and only worth making when the type said nothing that matched — which is
the common case, since `application/octet-stream` is what most uploads are
labelled by whatever put them there. A viewer claiming an exact type is listed
before one claiming the family it belongs to, or `text/` would swallow
`text/html` on its way past.

**HTML is shown as source and never rendered.** A blob is bytes someone
uploaded to a project, and this page holds an API key; rendering would run a
stranger's markup beside it.

**The registry's vote and the browser's vote are counted differently, and the
pdf viewer is where that bites.** The registry may pick a viewer from the key
when the stored type says nothing useful, but a browser decides what to do with
a response from its `Content-Type` header alone — so a pdf the store labelled
`application/octet-stream` is routed to the pdf viewer by its name and then
*downloaded* rather than drawn, because octet-stream is the header that means
"save this". Where the header already says pdf, the frame is pointed at the
signed URL and the browser streams it; where it does not, the bytes are fetched
once, checked for the `%PDF-` signature, and handed back through a blob URL
carrying the type. The signature check is what keeps the name from being taken
as evidence, and it is also why the frame needs no `sandbox` attribute: nothing
reaches it that has not either been labelled a pdf by the store or shown itself
to be one.

Source is the one viewer that must hold a whole blob to do its job, so it is
the only one with a ceiling: past 1 MB it says so and points at the file
instead. The others hand a URL to an element and let the browser stream it.

### The transport

Video and audio are the same problem wearing different clothes — one has a
picture and one does not, but both are a position in a duration — so both drive
one transport. It is built rather than borrowed because `controls` draws the
browser's own chrome, which is a different shape and weight in every browser
and matches none of them here. The seek bar stays an `<input type="range">`
underneath the paint, so arrow keys, `Home`, `End` and the screen reader's idea
of a slider all still work without being rebuilt. Its track is drawn in three
layers — played, fetched-but-unplayed, and not yet here — because the middle
one is the only place the console says whether a stall is the network or the
file.

## The blob tree

Blob keys are single strings — the slashes in them are part of the name and the
store has no folders — but people write them that way because they think in
folders, so the rail reads the separators back out. A branch is a consequence of
how the leaves beneath it were named and disappears with the last of them, so it
is drawn quieter than a leaf and carries a count where a leaf carries its state.

The find field above the tree narrows it in place. It matches against the whole
key, slashes included, and highlights the run of each segment the query covers —
so `day2/wreck` highlights across two rows. While a search is running the
heading reports `[shown of total]`, and folding is ignored, because a filtered
tree that hid its own matches behind a folded branch would be worse than a list.

## Layout

```
src/
  App.tsx                 state, the keyboard dispatcher, the command registry
  lib/api.ts              the API, and the signed-URL rewrite
  lib/sql.ts              statement building — the printed SQL comes from here
  lib/media.ts            signed download URLs, cached until they lapse
  lib/format.ts           bytes, latency, timestamps, running time
  lib/text.ts             bytes read as text, and the ceiling on doing so
  viewers/viewer.ts       what it takes to show a blob — the abstraction
  viewers/registry.ts     which viewer draws which bytes — the only list
  components/Shell.tsx    tabline · canvas · command line · statusline
  components/Rail.tsx     the workspace's pages and contents, and the j/k cursor
  components/*Pane.tsx    workspace · members · table · blob
  components/dialogs.tsx  every form
  vigil/                  the design system, vendored, plus the console's layer
```

## Known deviation from the handoff

`--vg-fg-muted` is overridden in `app.css` from `#5A5852` to `#7C7A74`.
§13 of `VIGIL-DESIGN-SYSTEM.md` asks for this: the shipped value measures
≈2.8:1 on the ground and carries most of the metadata in the system.
