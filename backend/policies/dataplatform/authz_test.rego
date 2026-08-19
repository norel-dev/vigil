# Tests for the dataplatform access policy.
#
# Run them with:  opa test policies -v
package dataplatform.authz_test

import data.dataplatform.authz
import rego.v1

alice := "11111111-1111-1111-1111-111111111111"

root := "33333333-3333-3333-3333-333333333333"

alices_project := "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

bobs_project := "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

# Alice owns her own project and holds no role anywhere else.
alice_subject := {
	"id": alice,
	"email": "alice@example.com",
	"is_platform_admin": false,
	"project_roles": {alices_project: "owner"},
}

# The platform administrator belongs to no project at all.
root_subject := {
	"id": root,
	"email": "root@example.com",
	"is_platform_admin": true,
	"project_roles": {},
}

# Datastores carry no project and no owner: their type says they belong to
# the platform, and that is all the policy needs to know.
warehouse := {
	"type": "datastore",
	"id": "warehouse",
	"project_id": null,
	"scope": "system",
}

lake := {
	"type": "datastore",
	"id": "lake",
	"project_id": null,
	"scope": "system",
}

alices_project_resource := {
	"type": "project",
	"id": alices_project,
	"project_id": alices_project,
	"scope": "project",
}

bobs_project_resource := {
	"type": "project",
	"id": bobs_project,
	"project_id": bobs_project,
	"scope": "project",
}

# Tables sit under a project, so they carry the project that governs them and
# are judged by the role the caller holds in it.
alices_table := {
	"type": "table",
	"id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
	"project_id": alices_project,
	"scope": "project",
}

bobs_table := {
	"type": "table",
	"id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
	"project_id": bobs_project,
	"scope": "project",
}

# Blobs sit under a project exactly as tables do, and are judged the same way.
alices_blob := {
	"type": "blob",
	"id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
	"project_id": alices_project,
	"scope": "project",
}

bobs_blob := {
	"type": "blob",
	"id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
	"project_id": bobs_project,
	"scope": "project",
}

with_role(role, project) := {
	"id": alice,
	"email": "alice@example.com",
	"is_platform_admin": false,
	"project_roles": {project: role},
}

# --- the case the platform exists to enforce --------------------------------

test_platform_admin_may_manage_datastores if {
	every action in ["datastore.create", "datastore.read", "datastore.query", "datastore.update", "datastore.delete"] {
		authz.allow with input as {
			"subject": root_subject,
			"action": action,
			"resource": warehouse,
		}
	}
}

test_a_regular_user_may_not_touch_a_datastore_at_all if {
	every action in ["datastore.create", "datastore.read", "datastore.query", "datastore.update", "datastore.delete"] {
		not authz.allow with input as {
			"subject": alice_subject,
			"action": action,
			"resource": warehouse,
		}
	}
}

test_owning_a_project_does_not_reach_the_datastores if {
	# Alice owns a project, which is the most a regular user can be, and it
	# still gets her nowhere near the platform's storage.
	not authz.allow with input as {
		"subject": alice_subject,
		"action": "datastore.query",
		"resource": warehouse,
	}
}

test_denial_of_a_datastore_explains_that_it_is_the_platforms if {
	decision := authz.decision with input as {
		"subject": alice_subject,
		"action": "datastore.query",
		"resource": warehouse,
	}

	decision.allow == false
	contains(decision.reason, "only platform administrators")
}

# --- project roles ----------------------------------------------------------

test_a_project_owner_may_do_everything_to_their_project if {
	every action in ["project.read", "project.update", "project.manage_members", "project.delete"] {
		authz.allow with input as {
			"subject": alice_subject,
			"action": action,
			"resource": alices_project_resource,
		}
	}
}

test_a_viewer_may_read_but_not_manage_members if {
	viewer := with_role("viewer", bobs_project)

	authz.allow with input as {
		"subject": viewer,
		"action": "project.read",
		"resource": bobs_project_resource,
	}

	not authz.allow with input as {
		"subject": viewer,
		"action": "project.manage_members",
		"resource": bobs_project_resource,
	}
}

test_an_admin_may_manage_members_but_not_delete_the_project if {
	admin := with_role("admin", bobs_project)

	authz.allow with input as {
		"subject": admin,
		"action": "project.manage_members",
		"resource": bobs_project_resource,
	}

	not authz.allow with input as {
		"subject": admin,
		"action": "project.delete",
		"resource": bobs_project_resource,
	}
}

test_a_role_in_one_project_says_nothing_about_another if {
	not authz.allow with input as {
		"subject": alice_subject,
		"action": "project.read",
		"resource": bobs_project_resource,
	}
}

test_denial_of_a_foreign_project_explains_the_missing_membership if {
	decision := authz.decision with input as {
		"subject": alice_subject,
		"action": "project.read",
		"resource": bobs_project_resource,
	}

	decision.allow == false
	contains(decision.reason, "is not a member of the project")
}

test_denial_by_role_explains_the_role_held if {
	decision := authz.decision with input as {
		"subject": with_role("viewer", bobs_project),
		"action": "project.delete",
		"resource": bobs_project_resource,
	}

	decision.allow == false
	contains(decision.reason, "viewer")
}

# --- tables -----------------------------------------------------------------

test_a_viewer_may_read_a_table_and_read_from_it if {
	viewer := with_role("viewer", bobs_project)

	every action in ["table.read", "table.query"] {
		authz.allow with input as {
			"subject": viewer,
			"action": action,
			"resource": bobs_table,
		}
	}
}

test_a_viewer_may_not_change_anything_about_a_table if {
	viewer := with_role("viewer", bobs_project)

	every action in ["table.write", "table.create", "table.delete"] {
		not authz.allow with input as {
			"subject": viewer,
			"action": action,
			"resource": bobs_table,
		}
	}
}

test_an_editor_may_write_to_a_table_but_not_make_or_destroy_one if {
	editor := with_role("editor", bobs_project)

	authz.allow with input as {
		"subject": editor,
		"action": "table.write",
		"resource": bobs_table,
	}

	every action in ["table.create", "table.delete"] {
		not authz.allow with input as {
			"subject": editor,
			"action": action,
			"resource": bobs_table,
		}
	}
}

test_an_admin_still_may_not_make_or_destroy_a_table if {
	# Managing who is in a project is not the same as claiming storage for it
	# or throwing its data away, which is reserved for the owner.
	admin := with_role("admin", bobs_project)

	every action in ["table.create", "table.delete"] {
		not authz.allow with input as {
			"subject": admin,
			"action": action,
			"resource": bobs_table,
		}
	}
}

test_an_owner_may_do_everything_to_a_table_in_their_project if {
	every action in ["table.read", "table.query", "table.write", "table.create", "table.delete"] {
		authz.allow with input as {
			"subject": alice_subject,
			"action": action,
			"resource": alices_table,
		}
	}
}

test_owning_one_project_reaches_no_table_in_another if {
	every action in ["table.read", "table.query", "table.write", "table.create", "table.delete"] {
		not authz.allow with input as {
			"subject": alice_subject,
			"action": action,
			"resource": bobs_table,
		}
	}
}

test_denial_of_a_table_write_explains_the_role_held if {
	decision := authz.decision with input as {
		"subject": with_role("viewer", bobs_project),
		"action": "table.write",
		"resource": bobs_table,
	}

	decision.allow == false
	contains(decision.reason, "viewer")
	contains(decision.reason, "table.write")
}

test_filtering_keeps_only_the_tables_the_caller_may_see if {
	allowed := authz.allowed_resource_ids with input as {
		"subject": alice_subject,
		"action": "table.read",
		"resources": [alices_table, bobs_table],
	}

	allowed == {alices_table.id}
}

# --- blobs ------------------------------------------------------------------
#
# The interesting line here is between 'blob.download' and 'blob.upload'. The
# API turns whichever the caller holds into a URL signed for exactly that one
# HTTP method, and once that URL is handed over the API sees nothing further -
# so if this policy gets the line wrong, nothing downstream will catch it.

test_a_viewer_may_read_a_blob_and_download_it if {
	viewer := with_role("viewer", bobs_project)

	every action in ["blob.read", "blob.download"] {
		authz.allow with input as {
			"subject": viewer,
			"action": action,
			"resource": bobs_blob,
		}
	}
}

test_a_viewer_may_not_upload_to_a_blob_or_make_or_destroy_one if {
	viewer := with_role("viewer", bobs_project)

	every action in ["blob.upload", "blob.create", "blob.delete"] {
		not authz.allow with input as {
			"subject": viewer,
			"action": action,
			"resource": bobs_blob,
		}
	}
}

test_an_editor_may_upload_to_a_blob_but_not_make_or_destroy_one if {
	editor := with_role("editor", bobs_project)

	authz.allow with input as {
		"subject": editor,
		"action": "blob.upload",
		"resource": bobs_blob,
	}

	every action in ["blob.create", "blob.delete"] {
		not authz.allow with input as {
			"subject": editor,
			"action": action,
			"resource": bobs_blob,
		}
	}
}

test_an_admin_still_may_not_make_or_destroy_a_blob if {
	admin := with_role("admin", bobs_project)

	every action in ["blob.create", "blob.delete"] {
		not authz.allow with input as {
			"subject": admin,
			"action": action,
			"resource": bobs_blob,
		}
	}
}

test_an_owner_may_do_everything_to_a_blob_in_their_project if {
	every action in ["blob.read", "blob.download", "blob.upload", "blob.create", "blob.delete"] {
		authz.allow with input as {
			"subject": alice_subject,
			"action": action,
			"resource": alices_blob,
		}
	}
}

test_owning_one_project_reaches_no_blob_in_another if {
	every action in ["blob.read", "blob.download", "blob.upload", "blob.create", "blob.delete"] {
		not authz.allow with input as {
			"subject": alice_subject,
			"action": action,
			"resource": bobs_blob,
		}
	}
}

test_denial_of_a_blob_upload_explains_the_role_held if {
	decision := authz.decision with input as {
		"subject": with_role("viewer", bobs_project),
		"action": "blob.upload",
		"resource": bobs_blob,
	}

	not decision.allow
	contains(decision.reason, "viewer")
	contains(decision.reason, "blob.upload")
}

test_filtering_keeps_only_the_blobs_the_caller_may_see if {
	allowed := authz.allowed_resource_ids with input as {
		"subject": alice_subject,
		"action": "blob.read",
		"resources": [alices_blob, bobs_blob],
	}

	allowed == {alices_blob.id}
}

test_platform_admin_reaches_blobs_in_projects_they_do_not_belong_to if {
	every action in ["blob.read", "blob.download", "blob.upload", "blob.create", "blob.delete"] {
		authz.allow with input as {
			"subject": root_subject,
			"action": action,
			"resource": bobs_blob,
		}
	}
}

# --- users ------------------------------------------------------------------

# A user is a system level object like a datastore: who exists on the platform,
# and what they may call it with, is the platform's own business.
some_user := {
	"type": "user",
	"id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
	"project_id": null,
	"scope": "system",
}

test_platform_admin_may_manage_users if {
	every action in ["user.create", "user.read", "user.issue_key"] {
		authz.allow with input as {
			"subject": root_subject,
			"action": action,
			"resource": some_user,
		}
	}
}

test_a_regular_user_may_not_manage_users if {
	every action in ["user.create", "user.read", "user.issue_key"] {
		not authz.allow with input as {
			"subject": alice_subject,
			"action": action,
			"resource": some_user,
		}
	}
}

test_a_user_may_not_issue_a_key_for_their_own_record_either if {
	# Alice asking about her own account still gets nowhere here, because the
	# API never poses that question: acting on yourself is answered by whose
	# key the request arrived on, not by this policy.
	alices_own_record := {
		"type": "user",
		"id": alice,
		"project_id": null,
		"scope": "system",
	}

	not authz.allow with input as {
		"subject": alice_subject,
		"action": "user.issue_key",
		"resource": alices_own_record,
	}
}

test_filtering_hides_every_user_from_a_regular_user if {
	allowed := authz.allowed_resource_ids with input as {
		"subject": alice_subject,
		"action": "user.read",
		"resources": [some_user],
	}

	count(allowed) == 0
}

# --- platform administrators ------------------------------------------------

test_platform_admin_reaches_projects_they_do_not_belong_to if {
	authz.allow with input as {
		"subject": root_subject,
		"action": "project.delete",
		"resource": bobs_project_resource,
	}
}

test_platform_admin_reaches_tables_in_projects_they_do_not_belong_to if {
	every action in ["table.read", "table.query", "table.write", "table.create", "table.delete"] {
		authz.allow with input as {
			"subject": root_subject,
			"action": action,
			"resource": bobs_table,
		}
	}
}

# --- list filtering ---------------------------------------------------------

test_filtering_hides_every_datastore_from_a_regular_user if {
	allowed := authz.allowed_resource_ids with input as {
		"subject": alice_subject,
		"action": "datastore.read",
		"resources": [warehouse, lake],
	}

	count(allowed) == 0
}

test_filtering_keeps_every_datastore_for_an_administrator if {
	allowed := authz.allowed_resource_ids with input as {
		"subject": root_subject,
		"action": "datastore.read",
		"resources": [warehouse, lake],
	}

	allowed == {"warehouse", "lake"}
}

test_filtering_keeps_only_the_projects_the_caller_belongs_to if {
	allowed := authz.allowed_resource_ids with input as {
		"subject": alice_subject,
		"action": "project.read",
		"resources": [alices_project_resource, bobs_project_resource],
	}

	allowed == {alices_project}
}

test_filtering_an_empty_list_allows_nothing if {
	allowed := authz.allowed_resource_ids with input as {
		"subject": root_subject,
		"action": "datastore.read",
		"resources": [],
	}

	count(allowed) == 0
}
