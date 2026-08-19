"""FastAPI dependencies that establish who is calling.

A request carries its API key in the standard place, `Authorization: Bearer
<key>`, and these dependencies are what turn it into a user. `CurrentUser` is
the caller; `CurrentSubject` is the same caller described the way the policy
expects to receive them, carrying every project role they hold.

Nothing here raises HTTP errors, which is why the scheme below is declared
with `auto_error=False`: FastAPI would otherwise answer a missing header
itself, and a request without a key would be refused in a different shape
from one with a key that has been revoked. Both surface as
`InvalidApiKeyError`, and `src.platform.error_handlers` decides what that looks like
on the wire.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.authz.policy import Subject
from src.features.users import service as users_service
from src.features.users.model import User
from src.identity import service as api_keys_service
from src.platform.dependencies import DatabaseSession
from src.platform.exceptions import InvalidApiKeyError

__all__ = ["CurrentSubject", "CurrentUser", "api_key_scheme", "current_subject", "current_user"]

#: The credential the OpenAPI document advertises, and what makes the Swagger
#: UI's `Authorize` button ask for an API key.
api_key_scheme = HTTPBearer(
    scheme_name="API key",
    description="Paste the API key you were issued.",
    auto_error=False,
)


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(api_key_scheme)],
    session: DatabaseSession,
) -> User:
    """Return the user whose API key the request carries.

    Args:
        credentials: The bearer credential taken from the request, if it had
            one.
        session: The open database session.

    Returns:
        User: The caller.

    Raises:
        InvalidApiKeyError: If the request carries no usable key.
    """
    if credentials is None:
        raise InvalidApiKeyError("This endpoint needs an API key")

    return api_keys_service.authenticate(session=session, key=credentials.credentials)


async def current_subject(
    user: Annotated[User, Depends(current_user)],
    session: DatabaseSession,
) -> Subject:
    """Describe the caller the way the policy expects to receive them.

    Args:
        user: The caller.
        session: The open database session.

    Returns:
        Subject: The caller, together with every project role they hold.
    """
    return users_service.describe_subject(session=session, user=user)


CurrentUser = Annotated[User, Depends(current_user)]
CurrentSubject = Annotated[Subject, Depends(current_subject)]
