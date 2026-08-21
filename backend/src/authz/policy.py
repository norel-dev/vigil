"""The vocabulary of authorization: who, what, and on which object.

These models are the contract between the API and whatever renders access
decisions. They are deliberately free of both HTTP and Rego: the endpoints
build them from their own request, the decision point serializes them into
whatever its engine expects.

The contract names the *scope* an object lives at, but not the rules that
apply there: that a datastore is part of the platform is a fact about the
model and belongs here, while who may therefore touch one is a policy
decision and belongs in `policies/`.
"""

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, Field, computed_field

from src.features.projects.model import ProjectRole
from src.platform.exceptions import ConfigurationError

__all__ = [
    "Action",
    "AuthorizationRequest",
    "Decision",
    "MembershipChange",
    "PolicyDecisionPoint",
    "Resource",
    "ResourceFilter",
    "ResourceScope",
    "ResourceType",
    "Subject",
]


class ResourceScope(StrEnum):
    """The level of the platform an object lives at.

    Scope is what decides *which* rules apply to an object, rather than what
    those rules are: a system scoped object is part of the platform itself and
    answers only to platform administrators, while a project scoped object
    belongs to a project and answers to the roles held in it.
    """

    SYSTEM = "system"
    PROJECT = "project"


class ResourceType(StrEnum):
    """The kind of object an action is performed on."""

    PROJECT = "project"
    DATASTORE = "datastore"
    TABLE = "table"
    BLOB = "blob"
    USER = "user"

    @property
    def scope(self) -> ResourceScope:
        """Return the level of the platform objects of this type live at.

        Returns:
            ResourceScope: The scope governing every object of this type.
        """
        return _SCOPES[self]


#: The scope of each resource type. Kept beside the enum rather than inside it
#: because a `StrEnum` member's value is its wire representation, and this is
#: the one place a new resource type has to declare where it belongs.
_SCOPES: dict[ResourceType, ResourceScope] = {
    ResourceType.PROJECT: ResourceScope.PROJECT,
    ResourceType.DATASTORE: ResourceScope.SYSTEM,
    ResourceType.TABLE: ResourceScope.PROJECT,
    ResourceType.BLOB: ResourceScope.PROJECT,
    ResourceType.USER: ResourceScope.SYSTEM,
}

if _unscoped := set(ResourceType) - _SCOPES.keys():
    raise ConfigurationError(
        "Every resource type must declare the scope it lives at, and these do "
        f"not: {', '.join(sorted(resource_type.value for resource_type in _unscoped))}."
    )


class Action(StrEnum):
    """Everything a caller can ask to do.

    Values are namespaced by resource type so that a policy can reason about
    a whole family of actions at once.
    """

    PROJECT_READ = "project.read"
    PROJECT_UPDATE = "project.update"
    PROJECT_DELETE = "project.delete"
    PROJECT_MANAGE_MEMBERS = "project.manage_members"

    DATASTORE_CREATE = "datastore.create"
    DATASTORE_READ = "datastore.read"
    DATASTORE_QUERY = "datastore.query"
    DATASTORE_UPDATE = "datastore.update"
    DATASTORE_DELETE = "datastore.delete"

    # Reading a table and reading *from* it are different questions: the first
    # is about the platform's record of the table, the second about the rows
    # inside it. `query` and `write` are what decide the privilege the
    # platform connects to the datastore with, so the split here is the same
    # split the engine will go on to enforce.
    TABLE_CREATE = "table.create"
    TABLE_READ = "table.read"
    TABLE_QUERY = "table.query"
    TABLE_WRITE = "table.write"
    TABLE_DELETE = "table.delete"

    # The same split as tables, drawn for the same reason. `read` is about the
    # platform's record of a blob, while `download` and `upload` are about the
    # bytes, and those two decide which signed URL the caller is handed. The
    # signature is the whole of the permission once it leaves the platform, so
    # the line drawn here is the line the object store goes on to enforce.
    BLOB_CREATE = "blob.create"
    BLOB_READ = "blob.read"
    BLOB_DOWNLOAD = "blob.download"
    BLOB_UPLOAD = "blob.upload"
    BLOB_DELETE = "blob.delete"

    # Who exists on the platform, and what they may call it with. These are
    # asked about somebody *else's* account: a caller managing their own keys
    # is not posing an access question, so no action here covers that.
    USER_CREATE = "user.create"
    USER_READ = "user.read"
    USER_ISSUE_KEY = "user.issue_key"


class Subject(BaseModel):
    """The caller an action is evaluated for.

    The subject carries its own project memberships rather than having the
    policy look them up. This keeps the decision point stateless: it never
    needs access to the platform database.
    """

    id: UUID
    email: str
    is_platform_admin: bool = False
    project_roles: dict[UUID, ProjectRole] = Field(
        default_factory=dict,
        description="Role held by this subject in each project they belong to.",
    )


class Resource(BaseModel):
    """The object an action is performed on.

    Args:
        type: The kind of object.
        id: Its identifier, as callers refer to it.
        project_id: The project that governs it, for project scoped objects.
    """

    type: ResourceType
    id: str | None = None
    project_id: UUID | None = None

    @computed_field
    @property
    def scope(self) -> ResourceScope:
        """Return the level of the platform this object lives at.

        The scope follows from the type, and is computed rather than supplied
        so that no caller can describe a system level object as a project one
        and have the policy judge it by project roles.

        Returns:
            ResourceScope: The scope the policy should judge this object by.
        """
        return self.type.scope


class MembershipChange(BaseModel):
    """The membership a request means to write.

    Holding `project.manage_members` is not on its own an answer to whether a
    particular change may be made: handing somebody the owner role is not the
    same act as handing them a viewer role, and taking the owner role away is
    not the same act as granting it. Both roles travel with the request so
    that the policy can tell those acts apart, rather than the API deciding in
    advance which question is worth asking.
    """

    current_role: ProjectRole | None = Field(
        default=None,
        description=(
            "The role the member holds now, or None if they are not yet a "
            "member of the project."
        ),
    )
    requested_role: ProjectRole = Field(
        description="The role the caller is asking to give them."
    )


class AuthorizationRequest(BaseModel):
    """A single question posed to the policy: may `subject` do `action`?"""

    subject: Subject
    action: Action
    resource: Resource
    membership_change: MembershipChange | None = Field(
        default=None,
        description=(
            "The role change being attempted, for a request that changes who "
            "belongs to a project. Absent from every other question."
        ),
    )


class Decision(BaseModel):
    """The policy's answer to an `AuthorizationRequest`."""

    allow: bool
    reason: str = Field(
        default="",
        description="Why the policy decided the way it did, for the caller.",
    )


class PolicyDecisionPoint(Protocol):
    """Renders a decision for a single authorization request."""

    async def decide(self, *, request: AuthorizationRequest) -> Decision:
        """Decide whether the request is allowed.

        Args:
            request: The question to answer.

        Returns:
            Decision: Whether the action is allowed, and why.

        Raises:
            PolicyDecisionPointError: If no decision could be rendered. Callers
                must treat this as a denial.
        """
        ...


class ResourceFilter(Protocol):
    """Narrows a set of resources down to the ones a subject may act on."""

    async def filter_allowed(
        self,
        *,
        subject: Subject,
        action: Action,
        resources: list[Resource],
    ) -> set[str]:
        """Return the ids of the resources `subject` may perform `action` on.

        Args:
            subject: The caller the resources are filtered for.
            action: The action the caller wants to perform on them.
            resources: The candidate resources.

        Returns:
            set[str]: The ids of the allowed subset of `resources`.

        Raises:
            PolicyDecisionPointError: If no decision could be rendered. Callers
                must treat this as an empty result.
        """
        ...
