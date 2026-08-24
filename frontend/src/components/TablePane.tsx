import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type QueryResponse, type Table, type Uuid } from "../lib/api";
import { Empty, Head, Problem } from "./bits";
import { AddColumnDialog, InsertRowDialog } from "./dialogs";
import { ROW_LIMIT, latency as fmtLatency, stamp } from "../lib/format";
import { isRead, selectStatement, verbOf } from "../lib/sql";
import type { Rights } from "../lib/authz";

export interface TableActions {
  addColumn: () => void;
  insertRow: () => void;
}

/**
 * One table.
 *
 * The console's one loud idea lives here: the statement is never hidden. Add
 * a column or insert a row through a form and the form prints the SQL it
 * composed before it runs it, because the platform does not read the statement
 * either — the engine accepts or refuses it, and a reader who never saw the
 * text cannot understand the refusal.
 */
export function TablePane(props: {
  project: Uuid;
  table: Table;
  /** The policy as the console reads it, asked per act rather than once. */
  rights: Rights;
  registerActions: (actions: TableActions | null) => void;
  onRan: (verb: string, seconds: number, rows: number | null) => void;
  onDeleted: () => void;
  onAskDelete: (confirm: { title: string; body: string; verb: string; run: () => Promise<void> }) => void;
}) {
  const [statement, setStatement] = useState(() => selectStatement(props.table.name, ROW_LIMIT));
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [overlay, setOverlay] = useState<"column" | "row" | null>(null);

  /**
   * Run one statement. Returns what went wrong, or null if nothing did.
   *
   * A statement run from a dialog reports its refusal inside that dialog, so
   * `quiet` keeps the message off the panel the reader cannot currently see.
   */
  const run = useCallback(
    async (text: string, options?: { quiet?: boolean }): Promise<string | null> => {
      setRunning(true);
      if (!options?.quiet) setProblem(null);
      try {
        const response = await api.query(props.project, props.table.name, text);
        const returned = Array.isArray(response.data) ? (response.data as unknown[][]) : [];
        const named = response.metadata.columns ?? [];
        if (named.length > 0) setColumns(named);
        setResult({ ...response, data: returned });
        props.onRan(verbOf(text), response.latency, isRead(text) ? returned.length : null);
        return null;
      } catch (error) {
        const message = error instanceof ApiError ? error.message : String(error);
        if (!options?.quiet) {
          setProblem(message);
          setResult(null);
        }
        return message;
      } finally {
        setRunning(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [props.project, props.table.name],
  );

  /** Reload from scratch: the shape and the first page of rows in one read. */
  const reload = useCallback(async () => {
    const text = selectStatement(props.table.name, ROW_LIMIT);
    setStatement(text);
    await run(text);
  }, [props.table.name, run]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    props.registerActions({
      addColumn: () => setOverlay("column"),
      insertRow: () => setOverlay("row"),
    });
    return () => props.registerActions(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.table.name]);

  const rows = result?.data ?? [];
  const read = isRead(statement);

  return (
    <div className="vg-stack">
      <header className="vg-head">
        <div>
          <div className="vg-eyebrow">
            <span>table</span>
            <span className="id">· {props.table.datastore_name}</span>
          </div>
          <h1 className="vg-title is-small">{props.table.name}</h1>
          <div className="vg-subtitle">
            {props.table.description ?? "no description was given when this table was created"}
          </div>
        </div>
        <div className="vg-head-side">
          <div className="vg-head-meta">
            <span>{props.table.datastore_name}</span>
            <span>·</span>
            <span>{props.rights.can("table.write") ? "read + write" : "read only"}</span>
            <span>·</span>
            <span>created {stamp(props.table.creation_date)}</span>
          </div>
          <div className="vg-row-flex">
            <button
              className="vg-btn is-primary"
              onClick={() => setOverlay("row")}
              disabled={!props.rights.can("table.write") || columns.length === 0}
            >
              insert row
            </button>
            <button
              className="vg-btn"
              onClick={() => setOverlay("column")}
              disabled={!props.rights.can("table.write")}
            >
              add column
            </button>
            <button
              className="vg-btn is-danger"
              disabled={!props.rights.can("table.delete")}
              onClick={() =>
                props.onAskDelete({
                  title: `Delete ${props.table.name}`,
                  body: `Deleting this table drops it and every row in it from ${props.table.datastore_name}, for good. Unlike forgetting a datastore, there is nothing left behind to reconnect to.`,
                  verb: "delete table",
                  run: async () => {
                    await api.deleteTable(props.project, props.table.name);
                    props.onDeleted();
                  },
                })
              }
            >
              delete
            </button>
          </div>
        </div>
      </header>

      <section>
        <Head
          title="Statement"
          desc="one statement, in the dialect the datastore speaks. it may read and change this table and alter its shape, but it cannot create or drop anything, or reach another table."
          note={`:${verbOf(statement)}`}
        />
        <div className="dp-well">
          <div className="dp-well-head">
            <span className="dp-well-verb">{verbOf(statement)}</span>
            <span className="dp-well-subject">· {props.table.name}</span>
            <span className="vg-spacer" />
            <span>{props.rights.can("table.write") ? "read + write" : "read only"}</span>
          </div>
          <div className="dp-well-body">
            <span className="dp-well-prompt" aria-hidden="true">
              :
            </span>
            <textarea
              className="dp-well-input"
              value={statement}
              spellCheck={false}
              aria-label="statement to run"
              placeholder={`SELECT * FROM ${props.table.name}`}
              onChange={(event) => setStatement(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault();
                  void run(statement);
                }
              }}
            />
          </div>
          <div className="dp-well-foot">
            <span>
              <kbd>⌘↵</kbd> run
            </span>
            <span className="vg-spacer" />
            <button className="vg-btn is-ghost" onClick={() => void reload()}>
              reset to select
            </button>
            <button className="vg-btn is-primary" onClick={() => void run(statement)} disabled={running}>
              {running ? "running…" : "run"}
            </button>
          </div>
        </div>
        {problem && (
          <div style={{ marginTop: 10 }}>
            <Problem>{problem}</Problem>
          </div>
        )}
      </section>

      <section>
        <Head
          title="Rows"
          count={result !== null && read ? rows.length : undefined}
          desc="what the last statement returned. statements that change rows return none, and say so rather than showing an empty grid."
        />
        {problem !== null ? (
          <Empty>
            the statement above was refused, so nothing came back. the engine's reason is printed
            with it — the platform does not check the statement itself, and neither reads nor
            rewrites it.
          </Empty>
        ) : result === null ? (
          <Empty>{running ? "running…" : "nothing has been run against this table yet."}</Empty>
        ) : !read ? (
          <Empty>
            the last statement — <code className="dp-inline-code">{verbOf(statement)}</code> — returns
            no rows. it finished in {fmtLatency(result.latency)}. run the select above to see what the
            table now holds.
          </Empty>
        ) : rows.length === 0 ? (
          <Empty>
            the table has no rows matching that statement. its shape is recorded — {columns.length}{" "}
            {columns.length === 1 ? "column" : "columns"} — so insert a row to put something in it.
          </Empty>
        ) : (
          <div className="vg-table-scroll">
            <table className="vg-table">
              <thead>
                <tr>
                  <th style={{ width: 40, color: "var(--vg-fg-muted)" }}>#</th>
                  {columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={index}>
                    <td className="vg-num" style={{ color: "var(--vg-fg-muted)" }}>
                      {index + 1}
                    </td>
                    {columns.map((column, cell) => (
                      <td key={column} title={String(row[cell] ?? "")}>
                        {row[cell] === null || row[cell] === undefined ? (
                          <span className="dp-cell-null">null</span>
                        ) : (
                          String(row[cell])
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {overlay === "column" && (
        <AddColumnDialog
          table={props.table.name}
          onDismiss={() => setOverlay(null)}
          onRun={async (sql) => {
            const failed = await run(sql, { quiet: true });
            if (failed) return failed;
            setOverlay(null);
            await reload();
            return null;
          }}
        />
      )}
      {overlay === "row" && (
        <InsertRowDialog
          table={props.table.name}
          columns={columns}
          onDismiss={() => setOverlay(null)}
          onRun={async (sql) => {
            const failed = await run(sql, { quiet: true });
            if (failed) return failed;
            setOverlay(null);
            await reload();
            return null;
          }}
        />
      )}
    </div>
  );
}
