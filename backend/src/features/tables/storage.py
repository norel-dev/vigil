"""What storage that holds tables can do, and at which privilege.

A datastore implementation describes *how* to reach some storage. This module
describes what it means for one to hold *tables*: an implementation that does
satisfies `TableStorage`, one that holds something else simply does not, and
the service layer asks before it tries. Nothing here makes a blob store stub
out a method about tables.

Everything is expressed in terms of privilege. Creating a table is not the
same act as writing rows into one, and the platform never tells them apart by
reading the SQL it was handed: it connects with the privilege the caller has
earned and lets the engine refuse the rest. That is why `create_table` and
`drop_table` are separate methods rather than statements a caller could send
to `query_table` — the privilege that can create is never the privilege a
caller is given.
"""

import re
from collections.abc import Sequence
from enum import StrEnum, auto
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator

from src.features.datastores.storage import DataStoreQuery, DataStoreQueryResponse

__all__ = [
    "ColumnDefinition",
    "QueryPrivilege",
    "TableStorage",
    "validate_identifier",
]

#: What a name has to look like to be safe to place in a statement. Names are
#: never parameterizable in SQL, so the only defence is refusing the ones that
#: could mean something other than a name.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

#: What a column type may be built from. Callers write the type in their own
#: engine's dialect, so this cannot be a list of known types; it can only make
#: sure the text stays a type. Letters, digits, spaces, underscores, brackets
#: and commas are enough for `VARCHAR(255)`, `DECIMAL(10, 2)`, `JSONB` and
#: `TIMESTAMP WITH TIME ZONE`, while leaving no way to end the statement and
#: start another.
_COLUMN_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_ (),]{0,63}$")


def validate_identifier(*, name: str, kind: str) -> str:
    """Return `name` if it is usable as a SQL identifier, and raise if not.

    Args:
        name: The name to check.
        kind: What the name names, used to explain a rejection.

    Returns:
        str: The name, unchanged.

    Raises:
        ValueError: If the name could be read as anything but an identifier.
    """
    if _IDENTIFIER.fullmatch(name) is None:
        raise ValueError(
            f"'{name}' is not a usable {kind}: it must start with a letter or "
            "underscore, continue with letters, digits or underscores, and be "
            "at most 63 characters long."
        )

    return name


class QueryPrivilege(StrEnum):
    """How much a single query is allowed to do.

    The privilege is chosen from the caller's role before a connection is
    opened, and is then the engine's to enforce. Neither level can create or
    drop anything: that privilege exists only inside `TableStorage` itself.
    """

    #: May read rows, and nothing else.
    READ_ONLY = auto()

    #: May read rows, change them, and alter the shape of the table.
    READ_WRITE = auto()


class ColumnDefinition(BaseModel):
    """One column of a table being created.

    The type is written in the dialect of whichever engine will hold the
    table, so the platform does not try to understand it. It only makes sure
    the text cannot be read as more than a type: this string is placed into a
    `CREATE TABLE` run at the one privilege level that can create and drop.
    """

    name: str = Field(description="Name of the column.", examples=["customer_id"])
    type: str = Field(
        description="The column's type, in the datastore's own SQL dialect.",
        examples=["INTEGER", "VARCHAR(255)", "TIMESTAMP"],
    )
    nullable: bool = Field(
        default=True, description="Whether the column may hold no value."
    )

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        """Reject column names that are not plain identifiers.

        Args:
            value: The proposed column name.

        Returns:
            str: The name, unchanged.

        Raises:
            ValueError: If the name is not a usable identifier.
        """
        return validate_identifier(name=value, kind="column name")

    @field_validator("type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        """Reject column types that could end the statement they sit in.

        Args:
            value: The proposed column type.

        Returns:
            str: The type, stripped of surrounding whitespace.

        Raises:
            ValueError: If the type contains anything but a type.
        """
        candidate = value.strip()
        if _COLUMN_TYPE.fullmatch(candidate) is None:
            raise ValueError(
                f"'{value}' is not a usable column type: a type may contain "
                "only letters, digits, spaces, underscores, brackets and commas."
            )

        return candidate


@runtime_checkable
class TableStorage(Protocol):
    """Storage that holds structured tables, kept apart by namespace.

    A datastore implementation satisfies this by holding tables the platform
    can provision; one that holds anything else simply does not, and the
    service layer asks before it tries. Implementations are not required to
    inherit from this: what matters is that they offer the three acts, not
    where they got them from.

    Every act names a `namespace`, which is the platform's way of saying "the
    part of this datastore belonging to one project". Namespaces are what let
    a table be called what its project calls it: two projects may each have a
    table named `customers`, because the two never share a namespace. How a
    namespace is realised is the implementation's business - a separate
    database file, a schema, a catalogue - and no caller ever names one.
    """

    async def create_table(
        self, *, namespace: str, name: str, columns: Sequence[ColumnDefinition]
    ) -> None:
        """Create a table called `name` inside `namespace`.

        This runs at the privilege that may create and drop, which is why it
        is a method here rather than a statement a caller could send.

        Args:
            namespace: The part of the datastore the table belongs in.
            name: Name of the table to create.
            columns: The columns it should have, in order.

        Raises:
            TableProvisioningError: If the table could not be created.
        """
        ...

    async def drop_table(self, *, namespace: str, name: str) -> None:
        """Destroy the table `name` in `namespace`, and everything in it.

        Args:
            namespace: The part of the datastore the table belongs in.
            name: Name of the table to destroy.

        Raises:
            TableProvisioningError: If the table could not be dropped.
        """
        ...

    async def query_table(
        self,
        *,
        namespace: str,
        name: str,
        query: DataStoreQuery,
        privilege: QueryPrivilege,
    ) -> DataStoreQueryResponse:
        """Run `query` against `name` in `namespace`, at no more than `privilege`.

        Implementations must reach the engine's own privilege machinery here
        rather than reading the statement: whatever `query` says, it must not
        be able to touch another table, nor to create or drop anything.

        Args:
            namespace: The part of the datastore the table belongs in.
            name: Name of the only table the query may touch.
            query: The statement to run.
            privilege: The most the statement is allowed to do.

        Returns:
            DataStoreQueryResponse: The rows, metadata and latency.

        Raises:
            QueryRefusedError: If the engine refused the statement as beyond
                `privilege`, or as reaching outside `name`.
            QueryFailedError: If the statement was allowed but did not run.
        """
        ...
