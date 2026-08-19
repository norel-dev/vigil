"""The people the platform knows about.

A user is the only actor in the platform. Everything else — a project, a
table, a blob — is something a user was granted a role over, and the record
here is what those grants point at.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

__all__ = ["User"]


class User(SQLModel, table=True):
    """A user of the platform.

    A user is a record the platform keeps, not an account held somewhere
    else: they are created by a platform administrator and they call the API
    with an `ApiKey` issued against this row.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(
        unique=True,
        index=True,
        description="How a user is referred to when granting them access.",
    )
    name: str
    is_platform_admin: bool = Field(
        default=False,
        description="Platform administrators bypass every project level check.",
    )
    creation_date: datetime = Field(default_factory=datetime.now)
