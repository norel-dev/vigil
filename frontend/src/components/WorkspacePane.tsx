import type { BlobView, Membership, Project, Table } from "../lib/api";
import type { Rights } from "../lib/authz";
import { Empty, Fact, Head, Loading } from "./bits";
import { ContactSheet } from "./ContactSheet";
import { stamp } from "../lib/format";

/**
 * The workspace, whole.
 *
 * This view answers what is in the workspace: the tables it owns and the
 * blobs it holds. Who may reach it is a separate question, asked by separate
 * people for separate reasons, and it is answered on its own page — the band
 * here only counts them, and leads there.
 */
export function WorkspacePane(props: {
  project: Project;
  /** What the reader may do here, said in the platform's own words. */
  role: string;
  tables: Table[];
  blobViews: BlobView[] | null;
  members: Membership[] | null;
  /** The policy as the console reads it, asked per act rather than once. */
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
          <div className="vg-subtitle">
            {props.project.description ?? "no description was given when this workspace was created"}
          </div>
        </div>
        <div className="vg-head-side">
          <div className="vg-row-flex">
            <span className="vg-chip">
              <span className="k">you are</span>
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
        <Fact label="tables" value={String(props.tables.length)} meta="structured data" />
        <Fact
          label="blobs"
          value={props.blobViews ? String(props.blobViews.length) : "—"}
          meta={props.blobViews ? `${filled} hold bytes` : "reading the store…"}
        />
        <Fact
          label="members"
          value={props.members ? String(props.members.length) : "—"}
          meta="people who may reach it"
          onOpen={props.onOpenMembers}
          title="open the members page"
        />
        <Fact label="created" value={stamp(props.project.creation_date)} meta="utc" />
      </div>

      <section>
        <Head
          title="Tables"
          count={props.tables.length}
          desc="structured data this workspace owns. the platform records the table; the rows live in the datastore holding it."
        >
          <button
            className="vg-btn is-ghost"
            onClick={props.onNewTable}
            disabled={!props.rights.can("table.create")}
          >
            create table
          </button>
        </Head>
        {props.tables.length === 0 ? (
          <Empty>
            no tables in this workspace yet. creating one claims storage inside a datastore the whole
            platform shares, so only the workspace owner may do it.
          </Empty>
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
        <Head
          title="Blobs"
          count={props.blobViews?.length}
          desc="files this workspace owns. the record exists the moment you create it; the bytes arrive when something uploads through the signed url."
        >
          <button
            className="vg-btn is-ghost"
            onClick={props.onNewBlob}
            disabled={!props.rights.can("blob.create")}
          >
            upload
          </button>
        </Head>
        {props.blobViews === null ? (
          <Loading what="the object store" />
        ) : props.blobViews.length === 0 ? (
          <Empty>
            nothing has been recorded here yet. uploading records the blob and hands back a url to
            send the bytes to.
          </Empty>
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
