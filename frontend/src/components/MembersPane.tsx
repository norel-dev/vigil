import type { Membership, Project } from "../lib/api";
import type { Rights } from "../lib/authz";
import { Empty, Head, Loading } from "./bits";

/** Workspace members and their roles. */
export function MembersPane(props: {
  project: Project;
  role: string;
  members: Membership[] | null;
  rights: Rights;
  onGrant: () => void;
  onRemove: (member: Membership) => void;
}) {
  return (
    <div className="vg-stack">
      <header className="vg-head">
        <div>
          <div className="vg-eyebrow">
            <span>members</span>
            <span className="id">· {props.project.id}</span>
          </div>
          <h1 className="vg-title is-small">{props.project.name}</h1>
        </div>
        <div className="vg-head-side">
          <div className="vg-row-flex">
            <span className="vg-chip">
              <span className="k">role</span>
              {props.role}
            </span>
          </div>
        </div>
      </header>

      <section>
        <Head title="Members" count={props.members?.length}>
          <button
            className="vg-btn is-ghost"
            onClick={props.onGrant}
            disabled={!props.rights.can("project.manage_members")}
          >
            grant access
          </button>
        </Head>
        {props.members === null ? (
          <Loading />
        ) : props.members.length === 0 ? (
          <Empty>no members</Empty>
        ) : (
          <div className="vg-list">
            {props.members.map((member) => {
              // Owners can't be removed.
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
                      title={refusal ?? undefined}
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
