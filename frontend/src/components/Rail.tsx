import { useEffect, useRef } from "react";
import type { BlobView, Table } from "../lib/api";
import type { Node } from "../lib/tree";
import { runs } from "../lib/tree";
import type { Rights } from "../lib/authz";

/** One row in the sidebar. `j`/`k` walk all rows as a single list. */
export type RailRow =
  | { id: "overview"; kind: "overview" }
  | { id: "members"; kind: "members" }
  | { id: string; kind: "table"; table: Table }
  | { id: string; kind: "branch"; path: string; name: string; depth: number; count: number }
  | { id: string; kind: "leaf"; key: string; name: string; depth: number; view: BlobView };

export function railRows(
  tables: Table[],
  visible: Node<BlobView>[],
): RailRow[] {
  const rows: RailRow[] = [
    { id: "overview", kind: "overview" },
    { id: "members", kind: "members" },
  ];
  for (const table of tables) rows.push({ id: `table:${table.name}`, kind: "table", table });
  for (const node of visible) {
    rows.push(
      node.kind === "branch"
        ? {
            id: `branch:${node.path}`,
            kind: "branch",
            path: node.path,
            name: node.name,
            depth: node.depth,
            count: node.count,
          }
        : {
            id: `blob:${node.path}`,
            kind: "leaf",
            key: node.path,
            name: node.name,
            depth: node.depth,
            view: node.item,
          },
    );
  }
  return rows;
}

/** Workspace pages, as opposed to tables and blobs. */
const isPage = (row: RailRow) => row.kind === "overview" || row.kind === "members";

/** Name with search matches highlighted. */
function Name({ path, name, query }: { path: string; name: string; query: string }) {
  return (
    <span className="vg-tree-name" title={path}>
      {runs(path, name, query).map((run, index) =>
        run.hit ? (
          <mark className="vg-mark" key={index}>
            {run.text}
          </mark>
        ) : (
          <span key={index}>{run.text}</span>
        ),
      )}
    </span>
  );
}

export function Rail(props: {
  rows: RailRow[];
  cursor: number;
  openId: string;
  rights: Rights;
  tableCount: number;
  blobTotal: number;
  blobShown: number;
  query: string;
  expanded: ReadonlySet<string>;
  onQuery: (value: string) => void;
  onOpen: (row: RailRow, newTab: boolean) => void;
  onNewTable: () => void;
  onNewBlob: () => void;
  findRef: React.RefObject<HTMLInputElement | null>;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.querySelector<HTMLElement>(".is-cursor")?.scrollIntoView({ block: "nearest" });
  }, [props.cursor]);

  const row = (item: RailRow, index: number) => {
    const on = item.id === props.openId;
    const cursor = index === props.cursor;
    const classes = [
      "vg-treerow",
      item.kind === "branch" ? "is-branch" : "",
      on ? "is-on" : "",
      cursor ? "is-cursor" : "",
    ]
      .filter(Boolean)
      .join(" ");

    const depth =
      item.kind === "branch" || item.kind === "leaf" ? item.depth : 0;

    return (
      <button
        key={item.id}
        className={classes}
        style={{ "--vg-depth": depth } as React.CSSProperties}
        aria-current={on ? "true" : undefined}
        aria-expanded={item.kind === "branch" ? props.expanded.has(item.path) : undefined}
        onClick={(event) => props.onOpen(item, event.metaKey || event.ctrlKey)}
        onAuxClick={(event) => {
          if (event.button === 1) {
            event.preventDefault();
            props.onOpen(item, true);
          }
        }}
      >
        <span className="vg-tree-rail" style={{ width: depth * 12 }} aria-hidden="true" />
        <span className="vg-tree-caret" aria-hidden="true">
          {cursor ? "›" : ""}
        </span>
        {item.kind === "branch" ? (
          <span className="vg-tree-twist" aria-hidden="true">
            {props.expanded.has(item.path) || props.query.trim() !== "" ? "▾" : "▸"}
          </span>
        ) : (
          <span className="vg-tree-twist" aria-hidden="true" />
        )}
        {item.kind === "overview" && <span className="vg-tree-name">overview</span>}
        {item.kind === "members" && <span className="vg-tree-name">members</span>}
        {item.kind === "table" && <span className="vg-tree-name">{item.table.name}</span>}
        {item.kind === "branch" && <Name path={item.path} name={item.name} query={props.query} />}
        {item.kind === "leaf" && <Name path={item.key} name={item.name} query={props.query} />}
        <span className="vg-tree-meta">
          {item.kind === "table"
            ? item.table.datastore_name
            : item.kind === "branch"
              ? item.count
              : item.kind === "leaf"
                ? item.view.stored
                  ? "filled"
                  : "empty"
                : ""}
        </span>
      </button>
    );
  };

  const pages = props.rows.filter(isPage);
  const tables = props.rows.filter((item) => item.kind === "table");
  const blobs = props.rows.filter((item) => item.kind === "branch" || item.kind === "leaf");
  const searching = props.query.trim() !== "";

  return (
    <nav className="vg-split-rail" aria-label="workspace contents" ref={ref}>
      <div className="dp-rail-group">
        <div className="vg-pick-title">workspace</div>
        <div className="vg-tree">
          {pages.map((item) => row(item, props.rows.indexOf(item)))}
        </div>
      </div>

      <div className="dp-rail-group">
        <div className="vg-pick-title">tables [{props.tableCount}]</div>
        <div className="vg-tree">
          {tables.length === 0 ? (
            <div className="vg-tree-empty">none yet</div>
          ) : (
            tables.map((item) => row(item, props.rows.indexOf(item)))
          )}
        </div>
        <div className="dp-rail-actions">
          <button
            className="vg-btn is-ghost"
            onClick={props.onNewTable}
            disabled={!props.rights.can("table.create")}
          >
            + table
          </button>
        </div>
      </div>

      <div className="dp-rail-group">
        <div className="vg-pick-title dp-rail-head">
          <span>
            blobs [{searching ? `${props.blobShown} of ${props.blobTotal}` : props.blobTotal}]
          </span>
        </div>

        <div className="vg-find">
          <span className="vg-find-sigil" aria-hidden="true">
            /
          </span>
          <input
            ref={props.findRef}
            className="vg-find-input"
            value={props.query}
            spellCheck={false}
            aria-label="search blobs"
            placeholder="search…"
            onChange={(event) => props.onQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.stopPropagation();
                if (props.query === "") event.currentTarget.blur();
                else props.onQuery("");
              }
            }}
          />
          {searching && (
            <button
              type="button"
              className="vg-find-clear"
              aria-label="clear search"
              onClick={() => props.onQuery("")}
            >
              ×
            </button>
          )}
        </div>

        <div className="vg-tree">
          {props.blobTotal === 0 ? (
            <div className="vg-tree-empty">none yet</div>
          ) : blobs.length === 0 ? (
            <div className="vg-tree-empty">no matches</div>
          ) : (
            blobs.map((item) => row(item, props.rows.indexOf(item)))
          )}
        </div>

        <div className="dp-rail-actions">
          <button
            className="vg-btn is-ghost"
            onClick={props.onNewBlob}
            disabled={!props.rights.can("blob.create")}
          >
            + upload
          </button>
        </div>
      </div>
    </nav>
  );
}
