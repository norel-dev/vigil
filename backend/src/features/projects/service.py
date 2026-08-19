"""Reading and writing projects and their membership.

Membership is what the policy reasons about, so every change to it goes
through this module rather than being written from an endpoint.
"""

from uuid import UUID

from sqlmodel import Session, select

from src.features.projects.model import Project, ProjectMember, ProjectRole
from src.features.users.model import User
from src.platform.exceptions import ObjectNotFoundError

__all__ = [
    "create_project",
    "get_project",
    "list_members",
    "list_projects",
    "roles_of_user",
    "set_member_role",
]


def create_project(
    *,
    session: Session,
    name: str,
    description: str | None,
    creator: User,
) -> Project:
    """Create a project and make its creator the owner.

    The creator is recorded as a member holding `ProjectRole.OWNER`, which is
    what later grants them access to everything inside the project.

    Args:
        session: The open database session.
        name: Name of the new project.
        description: Optional description of the new project.
        creator: The user creating the project.

    Returns:
        Project: The stored project.
    """
    project = Project(name=name, description=description)
    session.add(project)
    session.add(
        ProjectMember(project_id=project.id, user_id=creator.id, role=ProjectRole.OWNER)
    )
    session.commit()
    session.refresh(project)
    return project


def get_project(*, session: Session, project_id: UUID) -> Project:
    """Return the project with id `project_id`.

    Args:
        session: The open database session.
        project_id: Identifier of the project.

    Returns:
        Project: The stored project.

    Raises:
        ObjectNotFoundError: If no such project exists.
    """
    project = session.get(Project, project_id)
    if project is None:
        raise ObjectNotFoundError(object_type="project", identifier=str(project_id))

    return project


def list_projects(*, session: Session) -> list[Project]:
    """Return every project in the platform.

    The result is not filtered by access: that is the policy's job, and the
    caller is expected to run the result past it.

    Args:
        session: The open database session.

    Returns:
        list[Project]: All stored projects.
    """
    return list(session.exec(select(Project)).all())


def roles_of_user(*, session: Session, user_id: UUID) -> dict[UUID, ProjectRole]:
    """Return the role the user holds in each project they belong to.

    Args:
        session: The open database session.
        user_id: Identifier of the user.

    Returns:
        dict[UUID, ProjectRole]: Project id to role held in that project.
    """
    memberships = session.exec(
        select(ProjectMember).where(ProjectMember.user_id == user_id)
    ).all()
    return {membership.project_id: membership.role for membership in memberships}


def set_member_role(
    *,
    session: Session,
    project_id: UUID,
    user_id: UUID,
    role: ProjectRole,
) -> ProjectMember:
    """Grant `user_id` the role `role` in `project_id`, replacing any current one.

    Args:
        session: The open database session.
        project_id: The project to grant access to.
        user_id: The user being granted access.
        role: The role to grant.

    Returns:
        ProjectMember: The stored membership.
    """
    membership = session.get(ProjectMember, (project_id, user_id))
    if membership is None:
        membership = ProjectMember(project_id=project_id, user_id=user_id, role=role)
    else:
        membership.role = role

    session.add(membership)
    session.commit()
    session.refresh(membership)
    return membership


def list_members(*, session: Session, project_id: UUID) -> list[ProjectMember]:
    """Return every membership of the project `project_id`.

    Args:
        session: The open database session.
        project_id: Identifier of the project.

    Returns:
        list[ProjectMember]: The project's memberships.
    """
    return list(
        session.exec(
            select(ProjectMember).where(ProjectMember.project_id == project_id)
        ).all()
    )
