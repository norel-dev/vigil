import type { BlobView, Membership, Project, Table } from "../lib/api";
import type { Rights } from "../lib/authz";
import { Empty, Fact, Head, Loading } from "./bits";
import { ContactSheet } from "./ContactSheet";
import { stamp } from "../lib/format";

/** Workspace overview: tables and blobs. */
export function WorkspacePane(props: {
  project: Project;
  role: string;
  tables: Table[];
  blobViews: BlobView[] | null;
  members: Membership[] | null;
  rights: Rights;
  onOpenTable: (name: string) => void;
  onOpenBlob: (key: string) => void;
  onNewTable: () => void;
  onNewBlob: () => void;
  onOpenMembers: () => void;
}) {
  const filled = props.blobViews?.filter((view) => view.stored !== null).length ?? 0;

  return (
    <div className="vg-stack">
      <header className="vg-head">
        <div>
          <div className="vg-eyebrow">
            <span>workspace</span>
            <span className="id">· {props.project.id}</span>
          </div>
          <h1 className="vg-title">{props.project.name}</h1>
          {props.project.description && (
            <div className="vg-subtitle">{props.project.description}</div>
          )}
        </div>
        <div className="vg-head-side">
          <div className="vg-row-flex">
            <span className="vg-chip">
              <span className="k">role</span>
              {props.role}
            </span>
          </div>
          <div className="vg-row-flex">
            <button
              className="vg-btn is-primary"
              onClick={props.onNewTable}
              disabled={!props.rights.can("table.create")}
            >
              create table
            </button>
            <button
              className="vg-btn"
              onClick={props.onNewBlob}
              disabled={!props.rights.can("blob.create")}
            >
              upload
            </button>
          </div>
        </div>
      </header>

      <div className="vg-factband is-attached" style={{ marginTop: -18 }}>
        <Fact label="tables" value={String(props.tables.length)} />
        <Fact
          label="blobs"
          value={props.blobViews ? String(props.blobViews.length) : "—"}
          meta={props.blobViews ? `${filled} uploaded` : undefined}
        />
        <Fact
          label="members"
          value={props.members ? String(props.members.length) : "—"}
          onOpen={props.onOpenMembers}
          title="members"
        />
        <Fact label="created" value={stamp(props.project.creation_date)} meta="utc" />
      </div>

      <section>
        <Head title="Tables" count={props.tables.length}>
          <button
            className="vg-btn is-ghost"
            onClick={props.onNewTable}
            disabled={!props.rights.can("table.create")}
          >
            create table
          </button>
        </Head>
        {props.tables.length === 0 ? (
          <Empty>no tables yet</Empty>
        ) : (
          <div className="vg-gridtable">
            <div className="vg-gridtable-head" style={{ gridTemplateColumns: "1.4fr 1fr 1fr auto" }}>
              <span>name</span>
              <span>datastore</span>
              <span>description</span>
              <span>created</span>
            </div>
            {props.tables.map((table) => (
              <div
                key={table.id}
                className="vg-gridtable-row"
                style={{ gridTemplateColumns: "1.4fr 1fr 1fr auto" }}
                role="button"
                tabIndex={0}
                onClick={() => props.onOpenTable(table.name)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    props.onOpenTable(table.name);
                  }
                }}
              >
                <span className="vg-cell-value">{table.name}</span>
                <span className="vg-cell-key">{table.datastore_name}</span>
                <span className="vg-cell-key vg-truncate">{table.description ?? "—"}</span>
                <span className="vg-cell-num">{stamp(table.creation_date)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <Head title="Blobs" count={props.blobViews?.length}>
          <button
            className="vg-btn is-ghost"
            onClick={props.onNewBlob}
            disabled={!props.rights.can("blob.create")}
          >
            upload
          </button>
        </Head>
        {props.blobViews === null ? (
          <Loading />
        ) : props.blobViews.length === 0 ? (
          <Empty>no blobs yet</Empty>
        ) : (
          <ContactSheet
            project={props.project.id}
            views={props.blobViews}
            openKey={null}
            onOpen={props.onOpenBlob}
          />
        )}
      </section>
    </div>
  );
}
