import type { BlobView, Membership, Project, Table } from "../lib/api";
import type { Rights } from "../lib/authz";
import { Empty, Fact, Head, Loading } from "./bits";
import { ContactSheet } from "./ContactSheet";
import { stamp } from "../lib/format";

/**
 * The workspace, whole.
 *
 * A workspace is what objects belong to and what memberships are held
 * against, so this view answers three questions in order: what is in it, who
 * can reach it, and what it holds that can be looked at.
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
  onGrant: () => void;
  onRemove: (member: Membership) => void;
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

      <section>
        <Head
          title="Members"
          count={props.members?.length}
          desc="who may reach this workspace, and how far. roles are ordered, and each one includes everything below it."
        >
          <button
            className="vg-btn is-ghost"
            onClick={props.onGrant}
            disabled={!props.rights.can("project.manage_members")}
          >
            grant access
          </button>
        </Head>
        {props.members === null ? (
          <Loading what="the membership list" />
        ) : props.members.length === 0 ? (
          <Empty>
            nobody is listed against this workspace. you are reaching it as a platform administrator,
            who is trusted everywhere and is not a member of anything.
          </Empty>
        ) : (
          <div className="vg-list">
            {props.members.map((member) => {
              // An owner is permanent: the platform refuses to take one out,
              // by a fellow owner or by themselves, so the row says why rather
              // than offering a button that would come back refused.
              const refusal = props.rights.refusal(null, member.role);
              return (
                <div className="vg-listrow" key={member.user_id}>
                  <span className="vg-truncate">{member.email}</span>
                  <span className="vg-spacer" />
                  <span className="vg-tag">{member.role}</span>
                  {props.rights.can("project.remove_members") && (
                    <button
                      className="vg-btn is-ghost"
                      onClick={() => props.onRemove(member)}
                      disabled={refusal !== null}
                      title={refusal ?? `take ${member.email} out of this workspace`}
                    >
                      remove
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
