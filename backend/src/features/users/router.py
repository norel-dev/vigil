"""Endpoints for users and the API keys they call the platform with.

There are two halves here, and they answer to different rules.

The first is about *other people*: creating a user, listing who exists, and
issuing a key to somebody who has lost theirs. Users are part of the platform
rather than of anybody's project, so those go through the policy as system
scoped resources and reach only platform administrators.

The second is about the caller themselves — reading their own record,
and creating, listing and revoking their own keys. The policy is not asked
about those, and deliberately so: authentication has already established that
the caller is who the request acts on, so there is no access question left to
put to it. Every one of them is scoped to `current_user` in the handler, so
there is no path from these endpoints to somebody else's account.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, EmailStr, Field

from src.authz.policy import Action, Resource, ResourceType
from src.features.projects.model import ProjectRole
from src.features.users import service as users_service
from src.features.users.model import User
from src.identity import service as api_keys_service
from src.identity.caller import CurrentSubject, CurrentUser
from src.identity.model import ApiKey
from src.platform.dependencies import DatabaseSession, Enforcer

__all__ = ["create_users_router"]


class CurrentUserResponse(BaseModel):
    """Who the caller is, and what they are a member of."""

    id: UUID
    email: str
    is_platform_admin: bool
    project_roles: dict[UUID, ProjectRole]


class UserResponse(BaseModel):
    """A user of the platform."""

    id: UUID
    email: str
    name: str
    is_platform_admin: bool
    creation_date: datetime


class CreateUserRequest(BaseModel):
    """Request body for registering a user."""

    email: EmailStr = Field(description="Address the new user will be known by.")
    name: str = Field(description="Their display name.")
    is_platform_admin: bool = Field(
        default=False,
        description=(
            "Whether they bypass every project level check. Platform "
            "administrators are trusted everywhere, so grant this sparingly."
        ),
    )
    key_lifetime_days: int | None = Field(
        default=None,
        gt=0,
        description=(
            "How long the key issued alongside them should last. Leave unset "
            "for a key that does not expire."
        ),
    )


class CreateApiKeyRequest(BaseModel):
    """Request body for issuing an API key."""

    name: str = Field(
        description="What to call this key, so its holder can tell theirs apart.",
        examples=["laptop"],
    )
    lifetime_days: int | None = Field(
        default=None,
        gt=0,
        description="How many days the key should last. Unset means it never expires.",
    )


class ApiKeyResponse(BaseModel):
    """A key the platform holds, without the secret behind it."""

    id: UUID
    name: str
    creation_date: datetime
    expiration_date: datetime | None
    revocation_date: datetime | None


class IssuedApiKeyResponse(ApiKeyResponse):
    """A key that has just been created, including its secret.

    This is the only response that ever carries `api_key`. The platform keeps
    a digest of it and nothing more, so a key that is not saved out of this
    response is gone, and the way back is a new key rather than this one.
    """

    api_key: str = Field(description="The key itself. It is shown here and nowhere again.")


class CreatedUserResponse(BaseModel):
    """A user that has just been registered, with their first key."""

    user: UserResponse
    api_key: IssuedApiKeyResponse


def _as_resource(*, identifier: str) -> Resource:
    """Describe a user the way the policy expects to receive it.

    Users belong to the platform rather than to a project, so the type is
    enough for the policy to know which rules apply; the identifier is there
    to name the user in a refusal. Creating one has no id yet, so the address
    it would be given stands in.

    Args:
        identifier: How the caller referred to the user.

    Returns:
        Resource: The user, as the policy sees it.
    """
    return Resource(type=ResourceType.USER, id=identifier)


def _describe_key(*, key: ApiKey) -> ApiKeyResponse:
    """Describe a stored key for its holder.

    Args:
        key: The stored key.

    Returns:
        ApiKeyResponse: The key, without the secret behind it.
    """
    return ApiKeyResponse(
        id=key.id,
        name=key.name,
        creation_date=key.creation_date,
        expiration_date=key.expiration_date,
        revocation_date=key.revocation_date,
    )


def _describe_issued_key(*, issued: api_keys_service.IssuedApiKey) -> IssuedApiKeyResponse:
    """Describe a key that has just been created, secret included.

    Args:
        issued: The key and the secret behind it.

    Returns:
        IssuedApiKeyResponse: The key, as its new holder needs to receive it.
    """
    return IssuedApiKeyResponse(
        **_describe_key(key=issued.record).model_dump(),
        api_key=issued.secret,
    )


def _describe_user(*, user: User) -> UserResponse:
    """Describe a user.

    Args:
        user: The stored user.

    Returns:
        UserResponse: The user, as the API reports them.
    """
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        is_platform_admin=user.is_platform_admin,
        creation_date=user.creation_date,
    )


def create_users_router() -> APIRouter:
    """Build the users router.

    Returns:
        APIRouter: The router, ready to be included in the application.
    """
    router = APIRouter(prefix="/users", tags=["users"])

    @router.get("/me", response_model=CurrentUserResponse)
    async def read_current_user(subject: CurrentSubject) -> CurrentUserResponse:
        """Describe the caller and the roles they hold.

        This is exactly what is sent to the policy engine on every request,
        and the quickest way to check that a key works.
        """
        return CurrentUserResponse(
            id=subject.id,
            email=subject.email,
            is_platform_admin=subject.is_platform_admin,
            project_roles=subject.project_roles,
        )

    @router.post(
        "/me/api-keys",
        response_model=IssuedApiKeyResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_own_api_key(
        body: CreateApiKeyRequest,
        session: DatabaseSession,
        user: CurrentUser,
    ) -> IssuedApiKeyResponse:
        """Issue yourself another API key.

        This is how a key is rotated: create the new one, move over to it, and
        revoke the old one. The key comes back in full here and nowhere else.
        """
        issued = api_keys_service.issue_api_key(
            session=session,
            user=user,
            name=body.name,
            lifetime_days=body.lifetime_days,
        )
        return _describe_issued_key(issued=issued)

    @router.get("/me/api-keys", response_model=list[ApiKeyResponse])
    async def list_own_api_keys(
        session: DatabaseSession, user: CurrentUser
    ) -> list[ApiKeyResponse]:
        """List your own keys, revoked ones included.

        The secrets are not here and cannot be: the platform never kept them.
        """
        return [
            _describe_key(key=key)
            for key in api_keys_service.list_api_keys(session=session, user_id=user.id)
        ]

    @router.delete("/me/api-keys/{key_id}", response_model=ApiKeyResponse)
    async def revoke_own_api_key(
        key_id: UUID,
        session: DatabaseSession,
        user: CurrentUser,
    ) -> ApiKeyResponse:
        """Stop one of your keys from being accepted.

        The record stays, marked with when it was withdrawn, so a key that was
        once live remains something the platform can account for. Revoking the
        key the request itself arrived on works, and locks you out.
        """
        key = api_keys_service.revoke_api_key(
            session=session, user_id=user.id, key_id=key_id
        )
        return _describe_key(key=key)

    @router.post(
        "/", response_model=CreatedUserResponse, status_code=status.HTTP_201_CREATED
    )
    async def create_user(
        body: CreateUserRequest,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> CreatedUserResponse:
        """Register a user and issue them their first key.

        There is no sign in and no self registration, so this is the only way
        somebody comes to exist on the platform, and it is reserved for
        platform administrators. The key comes back once; hand it over out of
        band and it is theirs to rotate from then on.
        """
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.USER_CREATE,
            resource=_as_resource(identifier=body.email),
        )

        user = users_service.create_user(
            session=session,
            email=body.email,
            name=body.name,
            is_platform_admin=body.is_platform_admin,
        )
        issued = api_keys_service.issue_api_key(
            session=session,
            user=user,
            name="initial",
            lifetime_days=body.key_lifetime_days,
        )
        return CreatedUserResponse(
            user=_describe_user(user=user),
            api_key=_describe_issued_key(issued=issued),
        )

    @router.get("/", response_model=list[UserResponse])
    async def list_users(
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> list[UserResponse]:
        """List the users the caller is allowed to see.

        Like every other listing, this is filtered by the same policy that
        guards a direct read, so a caller who may not see users gets an empty
        list rather than a refusal.
        """
        users = users_service.list_users(session=session)
        allowed_ids = await enforcer.keep_allowed(
            subject=subject,
            action=Action.USER_READ,
            resources=[_as_resource(identifier=str(user.id)) for user in users],
        )
        return [
            _describe_user(user=user) for user in users if str(user.id) in allowed_ids
        ]

    @router.post(
        "/{user_id}/api-keys",
        response_model=IssuedApiKeyResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def issue_api_key_for_user(
        user_id: UUID,
        body: CreateApiKeyRequest,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> IssuedApiKeyResponse:
        """Issue a key to somebody else.

        This is the way back for a user who has lost every key they hold and
        can therefore no longer ask for one themselves. Handing out a
        credential that acts as another user is as far reaching as anything on
        the platform, so it is a platform administrator's to do.
        """
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.USER_ISSUE_KEY,
            resource=_as_resource(identifier=str(user_id)),
        )

        user = users_service.get_user(session=session, user_id=user_id)
        issued = api_keys_service.issue_api_key(
            session=session,
            user=user,
            name=body.name,
            lifetime_days=body.lifetime_days,
        )
        return _describe_issued_key(issued=issued)

    return router
