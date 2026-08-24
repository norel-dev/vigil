/**
 * The policy, as the console understands it.
 *
 * The platform decides this for itself, in rego, and its answer is the only
 * one that counts: nothing here grants anything. What this does is let the
 * console stop offering acts it already knows will be refused, so a reader
 * meets a button that is plainly not theirs rather than a 403 after the fact.
 *
 * That makes this a copy of `policies/dataplatform/authz.rego`, and copies
 * drift. It is kept rung for rung with that file, in the same order, so the
 * two can be read side by side; when the policy moves, this moves with it.
 */

import type { CurrentUser, ProjectRole, Uuid } from "./api";

/** One thing the policy can be asked about. Named exactly as the policy names it. */
export type Permission =
  | "project.read"
  | "project.update"
  | "project.delete"
  | "project.manage_members"
  | "project.remove_members"
  | "table.read"
  | "table.query"
  | "table.write"
  | "table.create"
  | "table.delete"
  | "blob.read"
  | "blob.download"
  | "blob.upload"
  | "blob.create"
  | "blob.delete";

const viewer: Permission[] = [
  "project.read",
  "table.read",
  "table.query",
  "blob.read",
  "blob.download",
];

const editor: Permission[] = [...viewer, "table.write", "blob.upload"];

const admin: Permission[] = [...editor, "project.update", "project.manage_members"];

// Creating claims storage the whole platform shares and deleting throws data
// away for good, so both sit at the top of the ladder rather than with the
// writing an editor does inside what already exists.
const owner: Permission[] = [
  ...admin,
  "project.delete",
  "project.remove_members",
  "table.create",
  "table.delete",
  "blob.create",
  "blob.delete",
];

const ROLE_PERMISSIONS: Record<ProjectRole, readonly Permission[]> = {
  viewer,
  editor,
  admin,
  owner,
};

/** What the reader may do in one workspace, and what the console may offer them. */
export interface Rights {
  /** The role they hold here, said in the platform's own words. */
  role: ProjectRole | "platform admin" | null;
  /** Whether the policy would allow `permission` on this workspace. */
  can: (permission: Permission) => boolean;
  /**
   * Whether they may put a member at `requested`, given the `current` role
   * that member holds — `null` for somebody who is not in the workspace yet.
   */
  mayGrant: (requested: ProjectRole, current: ProjectRole | null) => boolean;
  /** Whether they may take a member holding `current` out of the workspace. */
  mayRemove: (current: ProjectRole | null) => boolean;
  /** Why a membership change is refused, or null if it is not. */
  refusal: (requested: ProjectRole | null, current: ProjectRole | null) => string | null;
}

/**
 * Whether the policy's membership rules stand in the way of a change.
 *
 * Holding `project.manage_members` is not on its own an answer to whether a
 * particular change may be made: handing somebody the owner role is not the
 * same act as handing them viewer, and taking owner away is not the same act
 * as granting it. Removal arrives here as a change ending in no role at all,
 * because being put out of a workspace is being taken below every rung at
 * once, and it is refused for the same reason a demotion is.
 */
function changeForbidden(
  mine: ProjectRole | "platform admin" | null,
  requested: ProjectRole | null,
  current: ProjectRole | null,
): boolean {
  if (mine === "platform admin") return false;
  // Only an owner may create another owner: an admin's power over membership
  // stops short of the role that outranks their own.
  if (requested === "owner" && mine !== "owner") return true;
  // An owner is permanent. Nobody inside the workspace may lower one or put
  // one out, a fellow owner included, and that covers an owner doing it to
  // themselves.
  if (current === "owner" && requested !== "owner") return true;
  return false;
}

/** Read the reader's standing in one workspace off the identity the platform returned. */
export function rightsIn(me: CurrentUser | null, project: Uuid | null): Rights {
  const role: ProjectRole | "platform admin" | null = !me
    ? null
    : me.is_platform_admin
      ? "platform admin"
      : project
        ? (me.project_roles[project] ?? null)
        : null;

  // A platform administrator is trusted everywhere and is a member of nothing,
  // which is why their standing is not a rung on this ladder at all.
  const held: readonly Permission[] =
    role === "platform admin" ? owner : role ? ROLE_PERMISSIONS[role] : [];

  const can = (permission: Permission) =>
    role === "platform admin" || held.includes(permission);

  const refusal = (requested: ProjectRole | null, current: ProjectRole | null): string | null => {
    const needed: Permission =
      requested === null ? "project.remove_members" : "project.manage_members";
    if (!can(needed)) {
      return requested === null
        ? "taking somebody out of a workspace is the owner's to do"
        : "managing members takes an admin's rights";
    }
    if (!changeForbidden(role, requested, current)) return null;
    if (requested === "owner") return "only an owner may hand out the owner role";
    return current === "owner" && requested === null
      ? "an owner cannot be taken out of a workspace, by anybody, themselves included"
      : "the owner role cannot be taken back once it is granted";
  };

  return {
    role,
    can,
    mayGrant: (requested, current) => refusal(requested, current) === null,
    mayRemove: (current) => refusal(null, current) === null,
    refusal,
  };
}
