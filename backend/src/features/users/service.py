"""Reading and writing the platform's users.

There is no sign in and no self registration: a user exists because a
platform administrator created one, and calls the API with a key issued
against that record.
"""

from uuid import UUID

from loguru import logger
from sqlmodel import Session, select

from src.authz.policy import Subject
from src.features.projects import service as projects_service
from src.features.users.model import User
from src.platform.exceptions import DuplicateObjectError, ObjectNotFoundError

__all__ = [
    "create_user",
    "describe_subject",
    "find_user_by_email",
    "get_user",
    "list_users",
    "locate_user_by_email",
]


def create_user(
    *,
    session: Session,
    email: str,
    name: str,
    is_platform_admin: bool = False,
) -> User:
    """Register a new user of the platform.

    Args:
        session: The open database session.
        email: Address the user will be known by.
        name: Their display name.
        is_platform_admin: Whether they bypass every project level check.

    Returns:
        User: The stored user.

    Raises:
        DuplicateObjectError: If somebody already holds that address.
    """
    if session.exec(select(User).where(User.email == email)).first() is not None:
        raise DuplicateObjectError(object_type="user", identifier=email)

    user = User(email=email, name=name, is_platform_admin=is_platform_admin)
    session.add(user)
    session.commit()
    session.refresh(user)

    logger.info("Registered user {}", email)
    return user


def get_user(*, session: Session, user_id: UUID) -> User:
    """Return the user with id `user_id`.

    Args:
        session: The open database session.
        user_id: Identifier of the user.

    Returns:
        User: The stored user.

    Raises:
        ObjectNotFoundError: If no such user exists.
    """
    user = session.get(User, user_id)
    if user is None:
        raise ObjectNotFoundError(object_type="user", identifier=str(user_id))

    return user


def locate_user_by_email(*, session: Session, email: str) -> User | None:
    """Return the user registered with the address `email`, if there is one.

    Looking somebody up and insisting they exist are separate questions, and
    a caller who has not yet been allowed to ask about them should not learn
    the answer from a failure. This one only looks.

    Args:
        session: The open database session.
        email: The address to look up.

    Returns:
        User | None: The stored user, or None if nobody holds that address.
    """
    return session.exec(select(User).where(User.email == email)).first()


def find_user_by_email(*, session: Session, email: str) -> User:
    """Return the user registered with the address `email`.

    Args:
        session: The open database session.
        email: The address to look up.

    Returns:
        User: The stored user.

    Raises:
        ObjectNotFoundError: If nobody holds that address.
    """
    user = locate_user_by_email(session=session, email=email)
    if user is None:
        raise ObjectNotFoundError(object_type="user", identifier=email)

    return user


def list_users(*, session: Session) -> list[User]:
    """Return every user of the platform.

    The result is not filtered by access: that is the policy's job, and the
    caller is expected to run the result past it.

    Args:
        session: The open database session.

    Returns:
        list[User]: All stored users.
    """
    return list(session.exec(select(User)).all())


def describe_subject(*, session: Session, user: User) -> Subject:
    """Describe `user` the way the policy expects to receive them.

    Args:
        session: The open database session.
        user: The user to describe.

    Returns:
        Subject: The user, together with every project role they hold.
    """
    return Subject(
        id=user.id,
        email=user.email,
        is_platform_admin=user.is_platform_admin,
        project_roles=projects_service.roles_of_user(session=session, user_id=user.id),
    )
