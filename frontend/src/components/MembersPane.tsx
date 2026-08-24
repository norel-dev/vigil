import type { Membership, Project } from "../lib/api";
import type { Rights } from "../lib/authz";
import { Empty, Head, Loading } from "./bits";

/**
 * Who may reach one workspace, and how far.
 *
 * Membership is the workspace's access, not its contents, and the two change
 * for different reasons and at different people's hands — so it is read and
 * managed in a place of its own rather than under the inventory of what the
 * workspace holds.
 */
export function MembersPane(props: {
  project: Project;
  /** What the reader may do here, said in the platform's own words. */
  role: string;
  members: Membership[] | null;
  /** The policy as the console reads it, asked per act rather than once. */
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
          <div className="vg-subtitle">
            everyone listed against this workspace. the platform decides what each role may do;
            this page decides who holds one.
          </div>
        </div>
        <div className="vg-head-side">
          <div className="vg-row-flex">
            <span className="vg-chip">
              <span className="k">you are</span>
              {props.role}
            </span>
          </div>
        </div>
      </header>

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
