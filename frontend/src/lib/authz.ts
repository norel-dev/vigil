/**
 * Client-side mirror of `policies/dataplatform/authz.rego`, used only to
 * disable actions the server would refuse. Keep it in sync with the policy.
 */

import type { CurrentUser, ProjectRole, Uuid } from "./api";

/** Permission names, as in the policy. */
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

/** The current user's permissions in one workspace. */
export interface Rights {
  role: ProjectRole | "platform admin" | null;
  can: (permission: Permission) => boolean;
  /** `current` is the member's existing role, or null if they aren't a member. */
  mayGrant: (requested: ProjectRole, current: ProjectRole | null) => boolean;
  mayRemove: (current: ProjectRole | null) => boolean;
  /** Why a membership change is refused, or null if allowed. */
  refusal: (requested: ProjectRole | null, current: ProjectRole | null) => string | null;
}

/**
 * Owner-specific membership rules. `requested` is null for a removal.
 */
function changeForbidden(
  mine: ProjectRole | "platform admin" | null,
  requested: ProjectRole | null,
  current: ProjectRole | null,
): boolean {
  if (mine === "platform admin") return false;
  // Only owners can grant owner.
  if (requested === "owner" && mine !== "owner") return true;
  // Owners can't be demoted or removed.
  if (current === "owner" && requested !== "owner") return true;
  return false;
}

export function rightsIn(me: CurrentUser | null, project: Uuid | null): Rights {
  const role: ProjectRole | "platform admin" | null = !me
    ? null
    : me.is_platform_admin
      ? "platform admin"
      : project
        ? (me.project_roles[project] ?? null)
        : null;

  // Platform admins can do everything.
  const held: readonly Permission[] =
    role === "platform admin" ? owner : role ? ROLE_PERMISSIONS[role] : [];

  const can = (permission: Permission) =>
    role === "platform admin" || held.includes(permission);

  const refusal = (requested: ProjectRole | null, current: ProjectRole | null): string | null => {
    const needed: Permission =
      requested === null ? "project.remove_members" : "project.manage_members";
    if (!can(needed)) {
      return requested === null
        ? "requires owner"
        : "requires admin";
    }
    if (!changeForbidden(role, requested, current)) return null;
    if (requested === "owner") return "only owners can grant owner";
    return current === "owner" && requested === null
      ? "owners can't be removed"
      : "owners can't be demoted";
  };

  return {
    role,
    can,
    mayGrant: (requested, current) => refusal(requested, current) === null,
    mayRemove: (current) => refusal(null, current) === null,
    refusal,
  };
}
