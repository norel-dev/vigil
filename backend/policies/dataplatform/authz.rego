# The access policy of the dataplatform.
#
# The platform has two levels, and every resource states which one it belongs
# to in `resource.scope`:
#
#   system   the platform itself: the datastores it is built on, and the
#            users it knows. Only platform administrators may touch these.
#            A caller acting on their own account is not asked about here at
#            all — the API answers that from who the request came from,
#            because there is no access question in it.
#   project  a project and everything that sits under it, such as its tables
#            and its blobs. These answer to the role the caller holds in the
#            owning project.
package dataplatform.authz

import rego.v1

# What each project role may do inside its project.
#
# Tables are what finally separate the lower rungs of this ladder. A viewer may
# look at a table and read rows out of it; an editor may also change those rows
# and alter the table's shape; only an owner may bring a table into existence or
# destroy one, because creating a table claims storage the whole platform shares
# and dropping one throws data away for good.
#
# 'table.query' and 'table.write' are not two ways of saying the same thing. The
# API turns whichever of them the caller holds into the privilege it connects to
# the datastore with, so the line drawn here is the line the database engine
# itself goes on to enforce.
#
# Blobs follow the same ladder as tables, rung for rung. A viewer may see that
# a blob exists and download it; an editor may also replace its contents; only
# an owner may bring one into existence or destroy it. The reason is the same
# too: creating a blob claims a name in storage the whole platform shares, and
# deleting one throws the data away for good.
#
# 'blob.download' and 'blob.upload' are not two ways of saying the same thing.
# The API turns whichever the caller holds into a URL signed for exactly that
# one HTTP method, so the line drawn here is the line the object store itself
# goes on to enforce, without the API ever seeing the transfer.
viewer_permissions := {
	"project.read",
	"table.read",
	"table.query",
	"blob.read",
	"blob.download",
}

editor_permissions := viewer_permissions | {
	"table.write",
	"blob.upload",
}

admin_permissions := editor_permissions | {
	"project.update",
	"project.manage_members",
}

owner_permissions := admin_permissions | {
	"project.delete",
	"table.create",
	"table.delete",
	"blob.create",
	"blob.delete",
}

role_permissions := {
	"viewer": viewer_permissions,
	"editor": editor_permissions,
	"admin": admin_permissions,
	"owner": owner_permissions,
}

# Nothing is allowed unless a rule below says so.
default allow := false

allow if {
	is_allowed(input.subject, input.action, input.resource)
	not membership_change_forbidden
}

# The decision the API reads, carrying an explanation it can hand back to the
# caller when the answer is no.
decision := {
	"allow": allow,
	"reason": reason,
}

reason := "allowed" if allow

reason := sprintf(
	"%ss belong to the platform itself, and only platform administrators may act on them",
	[input.resource.type],
) if {
	not allow
	input.resource.scope == "system"
}

reason := sprintf(
	"%s is not a member of the project owning this %s",
	[input.subject.email, input.resource.type],
) if {
	not allow
	input.resource.scope == "project"
	not project_role
}

reason := sprintf(
	"%s holds the role '%s' in the owning project, which does not grant '%s'",
	[input.subject.email, project_role, input.action],
) if {
	not allow
	input.resource.scope == "project"
	project_role
	not is_allowed(input.subject, input.action, input.resource)
}

# A caller who may manage members and was still refused was refused by the
# membership rules below, so the answer says which of them stopped them.
reason := sprintf(
	"%s may manage this project's members, but only an owner may grant the 'owner' role",
	[input.subject.email],
) if {
	not allow
	project_role
	is_allowed(input.subject, input.action, input.resource)
	membership_change_forbidden
	input.membership_change.requested_role == "owner"
}

reason := sprintf(
	"the 'owner' role cannot be taken away once it is granted, so %s may not lower this member",
	[input.subject.email],
) if {
	not allow
	project_role
	is_allowed(input.subject, input.action, input.resource)
	membership_change_forbidden
	input.membership_change.requested_role != "owner"
}

# Filters a list of resources down to the ids the subject may act on, so that
# listing endpoints need a single round trip rather than one per row.
allowed_resource_ids contains resource.id if {
	some resource in input.resources
	is_allowed(input.subject, input.action, resource)
}

# --- the two ways to be allowed ---------------------------------------------

# Platform administrators are trusted everywhere. This is also the only rule
# that ever allows a system scoped resource: there is deliberately no second
# way to reach one, and the only way a project whose owner has left can be
# handed on to somebody else.
is_allowed(subject, _, _) if subject.is_platform_admin

# Everyone else acts on project scoped resources through the role they hold in
# the owning project.
is_allowed(subject, action, resource) if {
	resource.scope == "project"
	role := subject.project_roles[resource.project_id]
	action in role_permissions[role]
}

# --- the limits on changing membership --------------------------------------

# 'project.manage_members' is not a single act. Handing somebody the 'owner'
# role is not the same as handing them 'viewer', and taking 'owner' away is not
# the same as granting it, so holding the permission is not on its own an answer
# to whether a particular change may be made.
#
# A request that changes a membership therefore carries the role the member
# holds now and the role being asked for, and the two rules below judge the
# change itself, on top of the permission the caller holds. Every other question
# carries no membership change at all, so neither rule can speak to one.
default membership_change_forbidden := false

# Only an owner may create another owner. An admin's power over membership stops
# short of the role that outranks their own, or the ladder would have a rung
# anybody standing below it could climb.
membership_change_forbidden if {
	not input.subject.is_platform_admin
	input.membership_change.requested_role == "owner"
	input.subject.project_roles[input.resource.project_id] != "owner"
}

# An owner is permanent. Nobody inside the project may lower one, another owner
# included, and that covers an owner lowering themselves: co-owners hold the
# project jointly, and one of them quietly unseating the other is exactly what
# holding it jointly has to rule out.
membership_change_forbidden if {
	not input.subject.is_platform_admin
	input.membership_change.current_role == "owner"
	input.membership_change.requested_role != "owner"
}

# The role the caller holds in the project owning the resource of the question
# being decided, used to explain a denial.
project_role := input.subject.project_roles[input.resource.project_id]
