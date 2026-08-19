"""Issuing, using and withdrawing API keys.

This is the module that turns a string in an `Authorization` header into the
user behind it, and the only one that ever sees a key in full. Everything
above it works with a `User`.
"""

from datetime import datetime, timedelta
from uuid import UUID

from loguru import logger
from pydantic import BaseModel
from sqlmodel import Session, select

from src.features.users.model import User
from src.identity.keys import digest_of, generate_key
from src.identity.model import ApiKey
from src.platform.exceptions import InvalidApiKeyError, ObjectNotFoundError

__all__ = [
    "IssuedApiKey",
    "authenticate",
    "issue_api_key",
    "list_api_keys",
    "revoke_api_key",
]


class IssuedApiKey(BaseModel):
    """A freshly created key, together with the secret behind it.

    The secret exists in this form exactly once, on the way back to whoever
    asked for the key. It is never stored and cannot be recovered, so a caller
    who loses it needs a new key rather than a copy of this one.
    """

    record: ApiKey
    secret: str


def issue_api_key(
    *,
    session: Session,
    user: User,
    name: str,
    lifetime_days: int | None = None,
) -> IssuedApiKey:
    """Create a key for `user` and return it, in full, for the only time.

    Args:
        session: The open database session.
        user: The user the key will authenticate.
        name: What its holder will call it.
        lifetime_days: How many days the key should last. `None` leaves it
            without an expiry.

    Returns:
        IssuedApiKey: The stored record and the secret to hand over.
    """
    secret = generate_key()
    expiration_date = (
        datetime.now() + timedelta(days=lifetime_days) if lifetime_days is not None else None
    )

    record = ApiKey(
        user_id=user.id,
        name=name,
        secret_hash=digest_of(key=secret),
        expiration_date=expiration_date,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    logger.info("Issued API key '{}' to {}", name, user.email)
    return IssuedApiKey(record=record, secret=secret)


def authenticate(*, session: Session, key: str) -> User:
    """Return the user that `key` authenticates.

    Args:
        session: The open database session.
        key: The credential taken from the request.

    Returns:
        User: The user the key was issued to.

    Raises:
        InvalidApiKeyError: If the key is unknown, has been revoked, has
            expired, or belongs to a user that no longer exists. The caller is
            told none of those apart, because which one it is would say
            something about keys that were never theirs to learn about.
    """
    record = session.exec(
        select(ApiKey).where(ApiKey.secret_hash == digest_of(key=key))
    ).first()

    if record is None or not _is_usable(key=record):
        raise InvalidApiKeyError("The presented API key is not valid")

    user = session.get(User, record.user_id)
    if user is None:
        logger.warning("API key {} names a user that is gone", record.id)
        raise InvalidApiKeyError("The presented API key is not valid")

    return user


def _is_usable(*, key: ApiKey) -> bool:
    """Report whether `key` still stands.

    Args:
        key: The stored key.

    Returns:
        bool: True if the key has been neither revoked nor outlived.
    """
    if key.revocation_date is not None:
        return False

    return key.expiration_date is None or key.expiration_date > datetime.now()


def list_api_keys(*, session: Session, user_id: UUID) -> list[ApiKey]:
    """Return every key ever issued to `user_id`, revoked ones included.

    Args:
        session: The open database session.
        user_id: The user whose keys to list.

    Returns:
        list[ApiKey]: The user's keys, without the secrets behind them.
    """
    return list(
        session.exec(select(ApiKey).where(ApiKey.user_id == user_id)).all()
    )


def revoke_api_key(*, session: Session, user_id: UUID, key_id: UUID) -> ApiKey:
    """Stop `key_id` from being accepted, and record when that happened.

    The key is looked up within the user it belongs to, so one user's key id
    can never be used to withdraw another's.

    Args:
        session: The open database session.
        user_id: The user the key must belong to.
        key_id: The key to withdraw.

    Returns:
        ApiKey: The withdrawn key.

    Raises:
        ObjectNotFoundError: If that user holds no such key.
    """
    key = session.get(ApiKey, key_id)
    if key is None or key.user_id != user_id:
        raise ObjectNotFoundError(object_type="api key", identifier=str(key_id))

    if key.revocation_date is None:
        key.revocation_date = datetime.now()
        session.add(key)
        session.commit()
        session.refresh(key)
        logger.info("Revoked API key '{}' of user {}", key.name, user_id)

    return key
