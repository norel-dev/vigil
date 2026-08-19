"""Getting the first administrator into a platform that has none.

Every user is created by a platform administrator, and every key is issued by
one, which leaves an empty database with no way to reach itself. This module
is the way in: the administrators named in the configuration are brought into
being as the process starts, each already holding the key the configuration
gave them.

It runs on every start, not only the first, and says nothing new when there is
nothing new to say. That makes the configuration the standing description of
who the platform's administrators are, rather than a one-off instruction whose
effect nobody can see afterwards.
"""

from datetime import datetime

from loguru import logger
from sqlalchemy import Engine
from sqlmodel import Session, select

from src.features.users.model import User
from src.features.users.service import create_user
from src.identity.keys import digest_of
from src.identity.model import ApiKey
from src.platform.config import BootstrapAdminConfig
from src.platform.exceptions import ConfigurationError

__all__ = ["BOOTSTRAP_KEY_NAME", "ensure_bootstrap_admins"]

#: The name every key created from the configuration is stored under, so that
#: an administrator listing their keys can see which one came from there.
BOOTSTRAP_KEY_NAME = "bootstrap"


def ensure_bootstrap_admins(
    *, engine: Engine, admins: list[BootstrapAdminConfig]
) -> None:
    """Make sure every administrator in `admins` exists and can call the API.

    An administrator who is already there keeps their user record, and is
    promoted if somebody had taken the flag away. Their configured key is
    registered if the platform does not already hold its digest, so rotating
    a key is a matter of changing it here and restarting; the key it replaces
    is revoked rather than deleted.

    Args:
        engine: The engine of the platform's database.
        admins: The administrators the configuration declares.
    """
    if not admins:
        logger.warning(
            "No bootstrap platform administrators are configured, so nobody "
            "can register a datastore or create a user"
        )
        return

    with Session(engine) as session:
        for admin in admins:
            user = _ensure_administrator(session=session, admin=admin)
            _ensure_key(session=session, user=user, key=admin.api_key)


def _ensure_administrator(
    *, session: Session, admin: BootstrapAdminConfig
) -> User:
    """Return the user for `admin`, creating or promoting them as needed.

    Args:
        session: An open session on the platform's database.
        admin: The administrator the configuration declares.

    Returns:
        User: The stored user, holding the platform administrator flag.
    """
    user = session.exec(select(User).where(User.email == admin.email)).first()
    if user is None:
        return create_user(
            session=session,
            email=admin.email,
            name=admin.name,
            is_platform_admin=True,
        )

    if not user.is_platform_admin:
        logger.info("Promoting {} to platform administrator", user.email)
        user.is_platform_admin = True
        session.add(user)
        session.commit()
        session.refresh(user)

    return user


def _ensure_key(*, session: Session, user: User, key: str) -> None:
    """Make sure `key` is the key `user` authenticates with.

    Args:
        session: An open session on the platform's database.
        user: The administrator the key belongs to.
        key: The key the configuration gave them.

    Raises:
        ConfigurationError: If the platform has seen this key before in some
            other role — as a key that was withdrawn, or as somebody else's.
            Neither can be honoured, so the process refuses to start rather
            than start with a credential meaning something it did not mean.
    """
    secret_hash = digest_of(key=key)
    existing = session.exec(
        select(ApiKey).where(ApiKey.secret_hash == secret_hash)
    ).first()

    if existing is not None:
        _ensure_key_is_still_theirs(user=user, existing=existing)
        return

    superseded = session.exec(
        select(ApiKey).where(
            ApiKey.user_id == user.id,
            ApiKey.name == BOOTSTRAP_KEY_NAME,
            ApiKey.revocation_date == None,  # noqa: E711 - SQL, not Python
        )
    ).all()
    for previous in superseded:
        previous.revocation_date = datetime.now()
        session.add(previous)
        logger.info("Revoked the previous bootstrap key of {}", user.email)

    session.add(
        ApiKey(user_id=user.id, name=BOOTSTRAP_KEY_NAME, secret_hash=secret_hash)
    )
    session.commit()
    logger.info("Registered the configured bootstrap key of {}", user.email)


def _ensure_key_is_still_theirs(*, user: User, existing: ApiKey) -> None:
    """Check that a key the platform already knows still means what it should.

    Args:
        user: The administrator the configuration gives the key to.
        existing: The key the platform already holds under that digest.

    Raises:
        ConfigurationError: If the key was withdrawn, or belongs to somebody
            else.
    """
    if existing.user_id != user.id:
        raise ConfigurationError(
            f"The bootstrap key configured for {user.email} already belongs to "
            "another user. Generate a key of their own."
        )

    if existing.revocation_date is not None:
        raise ConfigurationError(
            f"The bootstrap key configured for {user.email} was revoked on "
            f"{existing.revocation_date}. A withdrawn key does not come back; "
            "generate a new one."
        )
