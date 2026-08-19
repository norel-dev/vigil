"""Projects, and the membership that governs everything inside them.

The platform has two levels. Objects at the *system* level, such as
datastores, describe the platform itself and are managed by platform
administrators. Objects at the *project* level belong to a project, and a
user's rights over them come from their membership in it. Membership is the
single source of truth for who may do what at that level, which is why
`Project` has no separate owner column: its owner is the member holding the
`ProjectRole.OWNER` role.
"""

from datetime import datetime
from enum import StrEnum, auto
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

__all__ = ["Project", "ProjectMember", "ProjectRole"]


class ProjectRole(StrEnum):
    """The role a user holds within a project.

    Roles are ordered from least to most privileged, and each role includes
    every permission of the roles below it. The mapping from role to concrete
    permissions is not defined here: it lives in the Rego policy, so that it
    can be changed without redeploying the API.
    """

    VIEWER = auto()
    EDITOR = auto()
    ADMIN = auto()
    OWNER = auto()


class Project(SQLModel, table=True):
    """A project is the space a user carves out for themselves.

    A project is what the objects inside it belong to, and what the
    memberships governing those objects are held against. Tables are the
    first such object: a project reaches the data in a datastore through one,
    never through the datastore itself.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: str | None = None
    creation_date: datetime = Field(default_factory=datetime.now)


class ProjectMember(SQLModel, table=True):
    """The role a single user holds in a single project."""

    project_id: UUID = Field(foreign_key="project.id", primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", primary_key=True)
    role: ProjectRole
    creation_date: datetime = Field(default_factory=datetime.now)
