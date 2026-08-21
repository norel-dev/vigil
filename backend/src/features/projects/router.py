"""Endpoints for projects and their membership.

Projects are the unit of access control: creating one is how a user carves
out a space that is theirs, and granting membership is how they let somebody
else in.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, status
from pydantic import BaseModel, EmailStr, Field

from src.authz.policy import Action, MembershipChange, Resource, ResourceType
from src.features.projects import service as projects_service
from src.features.projects.model import Project, ProjectRole
from src.features.users import service as users_service
from src.features.users.model import User
from src.identity.caller import CurrentSubject, CurrentUser
from src.platform.dependencies import DatabaseSession, Enforcer
from src.platform.exceptions import ObjectNotFoundError

__all__ = ["create_projects_router"]


class CreateProjectRequest(BaseModel):
    """Request body for creating a project."""

    name: str = Field(description="Unique name of the project.")
    description: str | None = Field(
        default=None, description="What the project is for."
    )


class GrantMembershipRequest(BaseModel):
    """Request body for granting somebody a role in a project."""

    email: EmailStr = Field(
        description=(
            "Address of the user to grant access to. They must already be "
            "a user of the platform."
        ),
    )
    role: ProjectRole = Field(description="The role to grant them.")


class ProjectMembershipResponse(BaseModel):
    """A user's role in a project."""

    user_id: UUID
    email: str
    role: ProjectRole


def _as_resource(*, project: Project) -> Resource:
    """Describe a project the way the policy expects to receive it.

    A project is governed by itself, which is what lets the role rules in the
    policy treat it like any other object.

    Args:
        project: The project to describe.

    Returns:
        Resource: The project, as the policy sees it.
    """
    return Resource(
        type=ResourceType.PROJECT,
        id=str(project.id),
        project_id=project.id,
    )


def create_projects_router() -> APIRouter:
    """Build the projects router.

    Returns:
        APIRouter: The router, ready to be included in the application.
    """
    router = APIRouter(prefix="/projects", tags=["projects"])

    @router.post("/", response_model=Project, status_code=status.HTTP_201_CREATED)
    async def create_project(
        body: CreateProjectRequest,
        session: DatabaseSession,
        user: CurrentUser,
    ) -> Project:
        """Create a project and become its owner.

        Any user of the platform may create a project. From then on, access
        to everything inside it is decided by the policy.
        """
        return projects_service.create_project(
            session=session,
            name=body.name,
            description=body.description,
            creator=user,
        )

    @router.get("/", response_model=list[Project])
    async def list_projects(
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> list[Project]:
        """List the projects the caller is allowed to see."""
        all_projects = projects_service.list_projects(session=session)
        allowed_ids = await enforcer.keep_allowed(
            subject=subject,
            action=Action.PROJECT_READ,
            resources=[_as_resource(project=project) for project in all_projects],
        )
        return [project for project in all_projects if str(project.id) in allowed_ids]

    @router.get("/{project_id}", response_model=Project)
    async def get_project(
        project_id: UUID,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> Project:
        """Read a single project."""
        project = projects_service.get_project(session=session, project_id=project_id)
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.PROJECT_READ,
            resource=_as_resource(project=project),
        )
        return project

    @router.get("/{project_id}/members", response_model=list[ProjectMembershipResponse])
    async def list_members(
        project_id: UUID,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> list[ProjectMembershipResponse]:
        """List who has access to a project, and with which role."""
        project = projects_service.get_project(session=session, project_id=project_id)
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.PROJECT_READ,
            resource=_as_resource(project=project),
        )

        memberships = projects_service.list_members(session=session, project_id=project_id)
        return [
            ProjectMembershipResponse(
                user_id=membership.user_id,
                email=member.email if (member := session.get(User, membership.user_id)) else "",
                role=membership.role,
            )
            for membership in memberships
        ]

    @router.put("/{project_id}/members", response_model=ProjectMembershipResponse)
    async def grant_membership(
        project_id: UUID,
        body: Annotated[GrantMembershipRequest, Body()],
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> ProjectMembershipResponse:
        """Grant a user a role in a project, replacing any role they hold.

        This is how somebody is let into a project: once they hold a role,
        the policy starts allowing them the actions that role covers, both on
        the project itself and on whatever comes to sit under it.

        Which role they hold now is as much a part of the question as the one
        being asked for, because the policy draws lines the permission alone
        does not: an owner is not a role every member manager may hand out,
        and not one that may be taken back.
        """
        project = projects_service.get_project(session=session, project_id=project_id)

        # The member is looked up before the decision but insisted on after
        # it, so that a caller who may not manage this project's membership
        # cannot use the refusal to learn which addresses the platform knows.
        member = users_service.locate_user_by_email(session=session, email=body.email)
        current_role = (
            None
            if member is None
            else projects_service.member_role(
                session=session, project_id=project_id, user_id=member.id
            )
        )

        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.PROJECT_MANAGE_MEMBERS,
            resource=_as_resource(project=project),
            membership_change=MembershipChange(
                current_role=current_role, requested_role=body.role
            ),
        )

        if member is None:
            raise ObjectNotFoundError(object_type="user", identifier=body.email)

        membership = projects_service.set_member_role(
            session=session,
            project_id=project_id,
            user_id=member.id,
            role=body.role,
        )
        return ProjectMembershipResponse(
            user_id=membership.user_id,
            email=member.email,
            role=membership.role,
        )

    @router.delete(
        "/{project_id}/members/{user_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def remove_membership(
        project_id: UUID,
        user_id: UUID,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> None:
        """Take a user out of a project, ending their access to everything in it.

        Removal is the owner's to decide rather than every member manager's:
        an admin shapes what the people in a project may do, while who is in
        it at all is the owner's call. An owner cannot be removed, by a fellow
        owner or by themselves, for the same reason one cannot be demoted.
        """
        project = projects_service.get_project(session=session, project_id=project_id)

        # As with granting, what the member holds now is read before the
        # decision and insisted on after it, so that a refusal says nothing
        # about who belongs to a project the caller may not manage.
        current_role = projects_service.member_role(
            session=session, project_id=project_id, user_id=user_id
        )

        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.PROJECT_REMOVE_MEMBERS,
            resource=_as_resource(project=project),
            membership_change=MembershipChange(current_role=current_role),
        )

        projects_service.remove_member(
            session=session, project_id=project_id, user_id=user_id
        )

    return router
