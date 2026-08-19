"""The vocabulary every datastore is described and reached by.

A datastore implementation describes *how* to reach some storage. What that
storage can hold is described per shape, beside the feature that holds it:
`src.features.tables.storage` for tables, `src.features.blobs.storage` for
blobs. What is here is only what both of those need and what every
implementation shares — the shape of data a store holds, the shape of a
statement and its answer, and how a project's corner of a store is named.

Nothing in this module imports anything else in the platform, and nothing
should be added to it that would: it sits underneath both the
implementations and the features that use them, so a cycle here would be a
cycle everywhere.
"""

from enum import StrEnum, auto
from typing import Any
from uuid import UUID

from pydantic import BaseModel

__all__ = [
    "DataStoreQuery",
    "DataStoreQueryResponse",
    "DataType",
    "namespace_of",
]


class DataType(StrEnum):
    """The shape of the data an object holds."""

    TABLE = auto()
    BLOB = auto()


def namespace_of(*, project_id: UUID) -> str:
    """Return the name of the part of a datastore belonging to `project_id`.

    A namespace is derived from the project rather than stored, because it is
    not a fact anybody chooses: it is only ever "this project's corner of that
    datastore". The letter in front keeps the result usable as both a SQL
    identifier and an S3 bucket name, neither of which would always accept a
    bare hexadecimal id.

    Args:
        project_id: The project whose namespace is wanted.

    Returns:
        str: The namespace name for that project.
    """
    return f"p{project_id.hex}"


class DataStoreQuery(BaseModel):
    """A single statement to run against some storage."""

    query: str


class DataStoreQueryResponse(BaseModel):
    """What running a statement produced."""

    data: Any
    metadata: dict
    latency: float
