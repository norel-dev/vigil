"""The credential a caller presents, as the platform stores it.

What a key *is* — how one is generated, and why a digest is enough — is
`src.identity.keys`. This module is only the row.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

__all__ = ["ApiKey"]


class ApiKey(SQLModel, table=True):
    """A credential a user calls the API with.

    The key itself is never stored. What is kept is a SHA-256 digest of it,
    which is what an incoming request is looked up by, so a copy of this
    table is of no use to whoever takes it. Digesting is enough here, and a
    password hash would not be: a key is 256 bits of randomness this platform
    generated, not something a person chose and could be guessed at.

    A key is never deleted. Revoking one records when it stopped being usable
    and leaves the row behind, so that what existed remains answerable after
    the fact.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        description="The user this key authenticates.",
    )
    name: str = Field(
        description="What its holder calls this key, so they can tell theirs apart."
    )
    secret_hash: str = Field(
        unique=True,
        index=True,
        description="SHA-256 digest, in hex, of the key that was handed out.",
    )
    creation_date: datetime = Field(default_factory=datetime.now)
    expiration_date: datetime | None = Field(
        default=None,
        description="When the key stops being accepted. Unset means never.",
    )
    revocation_date: datetime | None = Field(
        default=None,
        description="When the key was withdrawn. Unset means it still stands.",
    )
