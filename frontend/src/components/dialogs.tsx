import { useMemo, useState } from "react";
import {
  ApiError,
  api,
  uploadTo,
  type CatalogueEntry,
  type ColumnDefinition,
  type ProjectRole,
  type Uuid,
} from "../lib/api";
import { Dialog } from "./Overlay";
import { Field, Problem, Sketch } from "./bits";
import { addColumnStatement, createTableSketch, insertStatement, isIdentifier } from "../lib/sql";
import { bytes } from "../lib/format";

/* ============================================================================
   Every dialog that changes something prints what it is about to do first.
   For a table that is the statement itself; for an upload it is the two steps
   the platform actually takes, listed before either of them runs.
   ========================================================================== */

function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const submit = async (work: () => Promise<void>) => {
    setBusy(true);
    setProblem(null);
    try {
      await work();
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };
  return { busy, problem, setProblem, submit };
}

/* -- Workspaces ----------------------------------------------------------- */

export function NewWorkspaceDialog(props: {
  onDismiss: () => void;
  onCreated: (id: Uuid) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const { busy, problem, submit } = useSubmit();

  return (
    <Dialog eyebrow="workspace" title="Create a workspace" onDismiss={props.onDismiss} width={520}>
      <form
        className="dp-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(async () => {
            const project = await api.createProject(name.trim(), description.trim() || null);
            props.onCreated(project.id);
          });
        }}
      >
        <Field
          label="name"
          htmlFor="dp-ws-name"
          gloss="Names are unique across the platform, and this is what people will call the workspace."
        >
          <input
            id="dp-ws-name"
            className="vg-input is-lg"
            value={name}
            spellCheck={false}
            placeholder="field-recordings"
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field
          label="description"
          htmlFor="dp-ws-desc"
          gloss="What the workspace is for. Optional, and worth writing: it is what the next person reads."
        >
          <input
            id="dp-ws-desc"
            className="vg-input is-lg"
            value={description}
            placeholder="what this workspace is for"
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        {problem && <Problem>{problem}</Problem>}
        <div className="dp-form-actions">
          <span className="vg-spacer" />
          <button type="button" className="vg-btn is-ghost" onClick={props.onDismiss}>
            cancel
          </button>
          <button type="submit" className="vg-btn is-primary" disabled={busy || !name.trim()}>
            {busy ? "creating…" : "create workspace"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

export function GrantDialog(props: {
  project: Uuid;
  onDismiss: () => void;
  onGranted: () => void;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<ProjectRole>("editor");
  const { busy, problem, submit } = useSubmit();

  return (
    <Dialog eyebrow="membership" title="Grant access" onDismiss={props.onDismiss} width={520}>
      <form
        className="dp-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(async () => {
            await api.grantMembership(props.project, email.trim(), role);
            props.onGranted();
          });
        }}
      >
        <Field
          label="email"
          htmlFor="dp-grant-email"
          gloss="They must already be a user of the platform. Granting a role does not create one."
        >
          <input
            id="dp-grant-email"
            className="vg-input is-lg"
            type="email"
            value={email}
            spellCheck={false}
            placeholder="someone@example.com"
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>
        <Field
          label="role"
          htmlFor="dp-grant-role"
          gloss="Roles are ordered, and each includes everything below it. A viewer reads; an editor writes rows and uploads; an admin manages members; an owner may also create tables."
        >
          <select
            id="dp-grant-role"
            className="dp-select"
            value={role}
            onChange={(event) => setRole(event.target.value as ProjectRole)}
          >
            <option value="viewer">viewer</option>
            <option value="editor">editor</option>
            <option value="admin">admin</option>
            <option value="owner">owner</option>
          </select>
        </Field>
        {problem && <Problem>{problem}</Problem>}
        <div className="dp-form-actions">
          <span className="vg-spacer" />
          <button type="button" className="vg-btn is-ghost" onClick={props.onDismiss}>
            cancel
          </button>
          <button type="submit" className="vg-btn is-primary" disabled={busy || !email.trim()}>
            {busy ? "granting…" : "grant access"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

/* -- Tables ---------------------------------------------------------------- */

let seed = 0;
const nextId = () => `col-${(seed += 1)}`;

interface DraftColumn extends ColumnDefinition {
  id: string;
}

export function NewTableDialog(props: {
  project: Uuid;
  catalogue: CatalogueEntry[];
  onDismiss: () => void;
  onCreated: (name: string) => void;
}) {
  const stores = props.catalogue.filter((entry) => entry.data_type === "table");
  const [name, setName] = useState("");
  const [datastore, setDatastore] = useState(stores[0]?.name ?? "");
  const [description, setDescription] = useState("");
  const [columns, setColumns] = useState<DraftColumn[]>([
    { id: nextId(), name: "id", type: "INTEGER", nullable: false },
  ]);
  const { busy, problem, submit } = useSubmit();

  const complete = columns.filter((column) => column.name.trim() && column.type.trim());
  const nameOk = name.trim() === "" || isIdentifier(name.trim());
  const ready = isIdentifier(name.trim()) && datastore !== "" && complete.length === columns.length;

  const update = (id: string, patch: Partial<DraftColumn>) =>
    setColumns((all) => all.map((column) => (column.id === id ? { ...column, ...patch } : column)));

  return (
    <Dialog eyebrow="table" title="Create a table" onDismiss={props.onDismiss} width={640}>
      <form
        className="dp-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(async () => {
            await api.createTable(props.project, {
              name: name.trim(),
              datastore,
              description: description.trim() || null,
              columns: columns.map(({ name, type, nullable }) => ({
                name: name.trim(),
                type: type.trim(),
                nullable,
              })),
            });
            props.onCreated(name.trim());
          });
        }}
      >
        <div className="dp-field-pair">
          <Field
            label="name"
            htmlFor="dp-tbl-name"
            gloss="A plain SQL identifier. This is what members write in their statements."
          >
            <input
              id="dp-tbl-name"
              className="vg-input is-lg"
              value={name}
              spellCheck={false}
              placeholder="readings"
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field
            label="datastore"
            htmlFor="dp-tbl-store"
            gloss={
              stores.find((entry) => entry.name === datastore)?.description ??
              "Where the rows will actually live."
            }
          >
            <select
              id="dp-tbl-store"
              className="dp-select"
              value={datastore}
              onChange={(event) => setDatastore(event.target.value)}
            >
              {stores.map((entry) => (
                <option key={entry.name} value={entry.name}>
                  {entry.name}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {!nameOk && (
          <Problem>
            “{name.trim()}” is not a plain SQL identifier. Use letters, digits and underscores, and
            do not start with a digit.
          </Problem>
        )}

        <Field
          label="description"
          htmlFor="dp-tbl-desc"
          gloss="What the table is for. Optional."
        >
          <input
            id="dp-tbl-desc"
            className="vg-input is-lg"
            value={description}
            placeholder="what this table holds"
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>

        <div className="dp-field">
          <span className="dp-field-label">columns</span>
          <div className="dp-cols">
            {columns.map((column, index) => (
              <div className="dp-col-row" key={column.id}>
                <span className="dp-col-n">{index + 1}</span>
                <input
                  className="vg-input"
                  value={column.name}
                  spellCheck={false}
                  aria-label={`column ${index + 1} name`}
                  placeholder="name"
                  onChange={(event) => update(column.id, { name: event.target.value })}
                />
                <input
                  className="vg-input"
                  value={column.type}
                  spellCheck={false}
                  aria-label={`column ${index + 1} type`}
                  placeholder="TYPE"
                  onChange={(event) => update(column.id, { type: event.target.value })}
                />
                <button
                  type="button"
                  className={`vg-btn is-ghost${column.nullable ? "" : " is-on"}`}
                  aria-pressed={!column.nullable}
                  title={column.nullable ? "may hold no value" : "must hold a value"}
                  onClick={() => update(column.id, { nullable: !column.nullable })}
                >
                  {column.nullable ? "nullable" : "not null"}
                </button>
                <button
                  type="button"
                  className="vg-close"
                  aria-label={`remove column ${index + 1}`}
                  disabled={columns.length === 1}
                  onClick={() => setColumns((all) => all.filter((item) => item.id !== column.id))}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <span className="dp-field-gloss">
            Types are written in the dialect of whichever engine will hold the table — INTEGER, REAL,
            TEXT, VARCHAR(255), TIMESTAMP. The platform does not try to understand them.
          </span>
          <div>
            <button
              type="button"
              className="vg-btn is-ghost"
              onClick={() =>
                setColumns((all) => [...all, { id: nextId(), name: "", type: "TEXT", nullable: true }])
              }
            >
              + column
            </button>
          </div>
        </div>

        <div className="dp-field">
          <span className="dp-field-label">what will be created</span>
          <Sketch statement={createTableSketch(name.trim(), columns)} prompt="≡" />
          <span className="dp-field-gloss">
            A sketch, not the statement that runs. The platform writes the real one and generates the
            name the datastore holds it under, because that datastore holds other workspaces' tables
            too.
          </span>
        </div>

        {problem && <Problem>{problem}</Problem>}

        <div className="dp-form-actions">
          <span className="vg-spacer" />
          <button type="button" className="vg-btn is-ghost" onClick={props.onDismiss}>
            cancel
          </button>
          <button type="submit" className="vg-btn is-primary" disabled={busy || !ready}>
            {busy ? "creating…" : "create table"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

export function AddColumnDialog(props: {
  table: string;
  onDismiss: () => void;
  onRun: (sql: string) => Promise<string | null>;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState("TEXT");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const statement = addColumnStatement(props.table, name.trim(), type.trim());
  const ready = isIdentifier(name.trim()) && type.trim() !== "";

  return (
    <Dialog eyebrow="table" title="Add a column" onDismiss={props.onDismiss} width={560}>
      <form
        className="dp-form"
        onSubmit={(event) => {
          event.preventDefault();
          setBusy(true);
          void props
            .onRun(statement)
            .then(setProblem)
            .finally(() => setBusy(false));
        }}
      >
        <div className="dp-field-pair">
          <Field label="name" htmlFor="dp-col-name" gloss="A plain SQL identifier.">
            <input
              id="dp-col-name"
              className="vg-input is-lg"
              value={name}
              spellCheck={false}
              placeholder="depth"
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field label="type" htmlFor="dp-col-type" gloss="In the datastore's own dialect.">
            <input
              id="dp-col-type"
              className="vg-input is-lg"
              value={type}
              spellCheck={false}
              placeholder="REAL"
              onChange={(event) => setType(event.target.value)}
            />
          </Field>
        </div>

        <div className="dp-field">
          <span className="dp-field-label">what will run</span>
          <Sketch statement={statement} />
          <span className="dp-field-gloss">
            A column added to a table that already has rows must allow no value, so this one is added
            nullable. Every existing row will read null in it.
          </span>
        </div>

        {problem && <Problem>{problem}</Problem>}

        <div className="dp-form-actions">
          <span className="vg-spacer" />
          <button type="button" className="vg-btn is-ghost" onClick={props.onDismiss}>
            cancel
          </button>
          <button type="submit" className="vg-btn is-primary" disabled={busy || !ready}>
            {busy ? "altering…" : "add column"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

export function InsertRowDialog(props: {
  table: string;
  columns: string[];
  onDismiss: () => void;
  onRun: (sql: string) => Promise<string | null>;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const statement = useMemo(
    () =>
      insertStatement(
        props.table,
        props.columns.map((column) => ({ column, value: values[column] ?? "" })),
      ),
    [props.table, props.columns, values],
  );

  const filled = props.columns.filter((column) => (values[column] ?? "").trim() !== "").length;

  return (
    <Dialog eyebrow="table" title="Insert a row" onDismiss={props.onDismiss} width={620}>
      <form
        className="dp-form"
        onSubmit={(event) => {
          event.preventDefault();
          setBusy(true);
          void props
            .onRun(statement)
            .then(setProblem)
            .finally(() => setBusy(false));
        }}
      >
        <div className="dp-scroll-y">
          {props.columns.map((column) => (
            <Field key={column} label={column} identifier htmlFor={`dp-val-${column}`}>
              <input
                id={`dp-val-${column}`}
                className="vg-input is-lg"
                value={values[column] ?? ""}
                spellCheck={false}
                placeholder="leave blank for null"
                onChange={(event) =>
                  setValues((all) => ({ ...all, [column]: event.target.value }))
                }
              />
            </Field>
          ))}
        </div>

        <div className="dp-field">
          <span className="dp-field-label">what will run</span>
          <Sketch statement={statement} />
          <span className="dp-field-gloss">
            Anything that reads as a number is written as one; everything else is quoted. A blank
            field is left out of the statement entirely, so the column takes its default.
          </span>
        </div>

        {problem && <Problem>{problem}</Problem>}

        <div className="dp-form-actions">
          <span className="dp-field-gloss">
            {filled} of {props.columns.length} columns filled
          </span>
          <span className="vg-spacer" />
          <button type="button" className="vg-btn is-ghost" onClick={props.onDismiss}>
            cancel
          </button>
          <button type="submit" className="vg-btn is-primary" disabled={busy}>
            {busy ? "inserting…" : "insert row"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

/* -- Blobs ----------------------------------------------------------------- */

type StepState = "pending" | "running" | "done" | "failed";

export function UploadDialog(props: {
  project: Uuid;
  catalogue: CatalogueEntry[];
  onDismiss: () => void;
  onUploaded: (key: string) => void;
}) {
  const stores = props.catalogue.filter((entry) => entry.data_type === "blob");
  const [file, setFile] = useState<File | null>(null);
  const [key, setKey] = useState("");
  const [datastore, setDatastore] = useState(stores[0]?.name ?? "");
  const [description, setDescription] = useState("");
  const [over, setOver] = useState(false);
  const [steps, setSteps] = useState<[StepState, StepState]>(["pending", "pending"]);
  const [problem, setProblem] = useState<string | null>(null);
  const running = steps.includes("running");

  const take = (chosen: File) => {
    setFile(chosen);
    setProblem(null);
    if (key.trim() === "") setKey(`media/${chosen.name}`);
  };

  const send = async () => {
    if (!file) return;
    setProblem(null);
    setSteps(["running", "pending"]);
    try {
      const created = await api.createBlob(props.project, {
        key: key.trim(),
        datastore,
        content_type: file.type || "application/octet-stream",
        description: description.trim() || null,
      });
      setSteps(["done", "running"]);
      await uploadTo(created.upload, file);
      setSteps(["done", "done"]);
      props.onUploaded(created.blob.key);
    } catch (error) {
      setSteps(([first]) => [first === "running" ? "failed" : first, first === "running" ? "pending" : "failed"]);
      setProblem(error instanceof ApiError ? error.message : String(error));
    }
  };

  const mark = (state: StepState) =>
    state === "done" ? "✓" : state === "failed" ? "✗" : state === "running" ? "›" : "·";

  return (
    <Dialog eyebrow="blob" title="Upload a file" onDismiss={props.onDismiss} width={620}>
      <form
        className="dp-form"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <label
          className={`dp-drop${over ? " is-over" : ""}${file ? " is-loaded" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(event) => {
            event.preventDefault();
            setOver(false);
            const dropped = event.dataTransfer.files[0];
            if (dropped) take(dropped);
          }}
        >
          <input
            type="file"
            hidden
            accept="image/*,video/*,audio/*,*/*"
            onChange={(event) => {
              const chosen = event.target.files?.[0];
              if (chosen) take(chosen);
            }}
          />
          {file ? (
            <>
              <strong style={{ color: "var(--vg-fg-primary)", fontWeight: 400 }}>{file.name}</strong>
              <span>
                {bytes(file.size)} · {file.type || "type unstated"}
              </span>
              <span>choose another, or drop one here</span>
            </>
          ) : (
            <>
              <span>drop a photo or a video here</span>
              <span style={{ color: "var(--vg-interactive)" }}>or choose a file</span>
            </>
          )}
        </label>

        <div className="dp-field-pair">
          <Field
            label="key"
            htmlFor="dp-blob-key"
            gloss="What the workspace will call it. Slashes are part of the name rather than folders, so nothing has to be created first."
          >
            <input
              id="dp-blob-key"
              className="vg-input is-lg"
              value={key}
              spellCheck={false}
              placeholder="media/sunrise.jpg"
              onChange={(event) => setKey(event.target.value)}
            />
          </Field>
          <Field
            label="datastore"
            htmlFor="dp-blob-store"
            gloss={
              stores.find((entry) => entry.name === datastore)?.description ??
              "Where the bytes will actually live."
            }
          >
            <select
              id="dp-blob-store"
              className="dp-select"
              value={datastore}
              onChange={(event) => setDatastore(event.target.value)}
            >
              {stores.map((entry) => (
                <option key={entry.name} value={entry.name}>
                  {entry.name}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="description" htmlFor="dp-blob-desc" gloss="What the file is. Optional.">
          <input
            id="dp-blob-desc"
            className="vg-input is-lg"
            value={description}
            placeholder="what this file is"
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>

        <div className="dp-field">
          <span className="dp-field-label">what will happen</span>
          <ul className="vg-steps">
            <li className={`vg-step is-${steps[0]}`}>
              <span className="vg-step-mark">{mark(steps[0])}</span>
              <span className="vg-step-name">record</span>
              <span className="vg-step-desc">
                the platform writes down the blob and hands back a url to upload through
              </span>
            </li>
            <li className={`vg-step is-${steps[1]}`}>
              <span className="vg-step-mark">{mark(steps[1])}</span>
              <span className="vg-step-name">send</span>
              <span className="vg-step-desc">
                the bytes go straight to the store, signed for one put of this one key
              </span>
            </li>
          </ul>
        </div>

        {problem && <Problem>{problem}</Problem>}

        <div className="dp-form-actions">
          <span className="vg-spacer" />
          <button type="button" className="vg-btn is-ghost" onClick={props.onDismiss}>
            cancel
          </button>
          <button
            type="submit"
            className="vg-btn is-primary"
            disabled={running || !file || key.trim() === "" || datastore === ""}
          >
            {running ? "uploading…" : "upload"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

/* -- Destruction ----------------------------------------------------------- */

export function ConfirmDialog(props: {
  title: string;
  body: string;
  verb: string;
  onDismiss: () => void;
  run: () => Promise<void>;
}) {
  const { busy, problem, submit } = useSubmit();

  return (
    <Dialog eyebrow="confirm" title={props.title} onDismiss={props.onDismiss} width={520}>
      <div className="dp-form">
        <p className="vg-prose" style={{ margin: 0 }}>
          {props.body}
        </p>
        {problem && <Problem>{problem}</Problem>}
        <div className="dp-form-actions">
          <span className="vg-spacer" />
          <button type="button" className="vg-btn is-ghost" onClick={props.onDismiss}>
            cancel
          </button>
          <button
            type="button"
            className="vg-btn is-danger"
            disabled={busy}
            onClick={() => void submit(props.run)}
          >
            {busy ? "working…" : props.verb}
          </button>
        </div>
      </div>
    </Dialog>
  );
}
