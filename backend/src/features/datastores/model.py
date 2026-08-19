"""Module for datastore related code.

The idea of this module is to allow administrators of the
datastore to easily add and remove custom and dynamic datastores,
seperated for physical hardware or latency differences.

For example, if one would want to store data labeled "REAL_TIME"
on a really fast postgres that is directly connected to the API,
they would create a datastore that points to that postgres, and
store all other data on a different datastore that is run on AWS.

The abstraction model is as follows:
    1.  DataStore object defines the fields that describe a datastore
    2.  Each DataStore has an "implementation", which is the protocol
        or library used to interact with the underlying storage
    3.  Each "implementation" has its own custom fields for configuration
        plus a discriminated field that defines it's type (Table, BLOB, PDF)

The implementations themselves live in `src.features.datastores.implementations`,
one module each. This module is where they are gathered into the union the API
accepts and the database stores, and is deliberately the only place that names
all of them:
adding a store means writing a new module and adding it to the union here.
"""

from datetime import datetime
from enum import StrEnum, auto
from typing import Annotated, Any

from pydantic import TypeAdapter
from sqlalchemy import JSON, Dialect, TypeDecorator
from sqlmodel import Field, SQLModel

from src.features.datastores.implementations import (
    DataStoreImplementationBase,
    MinIODataStore,
    SQLiteDataStore,
)

__all__ = [
    "DataStore",
    "DataStoreImplementationBase",
    "DataStoreImplementationColumn",
    "DataStoreImplementations",
    "DataStoreVisibility",
    "MinIODataStore",
    "SQLiteDataStore",
]


class DataStoreVisibility(StrEnum):
    """Whether a datastore is offered to the platform, or only registered on it.

    This is about discovery and nothing else. A public datastore appears in
    the catalogue every authenticated caller reads, so anybody can find it and
    choose it. A private one does not appear there, so the only way to name it
    is to have been told it.

    What visibility deliberately does *not* do is decide access. A caller who
    knows the name of a private datastore can put a table or a blob in it
    exactly as they could a public one, because none of the rules that govern
    a datastore consult this field. Making a datastore private hides it; it
    does not protect it, and it must not be relied on as though it did.
    """

    PUBLIC = auto()
    PRIVATE = auto()


DataStoreImplementations = Annotated[
    SQLiteDataStore | MinIODataStore,
    Field(discriminator="implementation")
]

#: Serializer of the implementation column, used only by the column below.
_IMPLEMENTATION_ADAPTER: TypeAdapter[DataStoreImplementations] = TypeAdapter(
    DataStoreImplementations
)

#: Handed to the serializer when the destination is the platform's own
#: database rather than a caller. An implementation that holds a secret keeps
#: it out of every dump except this one, so the redaction is the default and
#: revealing it takes saying so.
PERSISTING = {"reveal_secrets": True}


class DataStoreImplementationColumn(TypeDecorator):
    """Stores an implementation as JSON, and reads it back as itself.

    Without this, the column would hand back the plain dictionary it holds,
    and every reader would have to rebuild the implementation from it before
    being able to use it. Parsing belongs here, at the one boundary where the
    conversion actually happens.
    """

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        """Write the implementation to the database as plain JSON.

        This is the one dump that asks for secrets in the clear, because it is
        the one destination that has to be able to reconnect afterwards.

        Args:
            value: The implementation being stored, or None.
            dialect: The dialect of the database being written to.

        Returns:
            Any: The JSON document to store, or None.
        """
        if value is None:
            return None

        return _IMPLEMENTATION_ADAPTER.dump_python(value, mode="json", context=PERSISTING)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        """Read the implementation back as the concrete type it was stored as.

        Args:
            value: The stored JSON document, or None.
            dialect: The dialect of the database being read from.

        Returns:
            Any: The implementation described by the document, or None.
        """
        if value is None:
            return None

        return _IMPLEMENTATION_ADAPTER.validate_python(value)


class DataStore(SQLModel, table=True):
    """Datastores are metadata that describe how to store and retrieve data.

    A datastore could be a Filesystem, a Query Engine,
    a Database or even multiple of these combined.

    A datastore is part of the platform itself rather than of any project: it
    describes hardware the whole platform shares, so it belongs to nobody and
    only platform administrators manage it. Projects reach the data behind a
    datastore through objects of their own, never through the datastore.

    `visibility` decides whether the platform offers the datastore to its
    users or merely knows about it. It is the one field here that says nothing
    about the storage: see `DataStoreVisibility` for what it does and, more
    importantly, what it does not do.
    """

    name: str = Field(primary_key=True)
    implementation: DataStoreImplementations = Field(sa_type=DataStoreImplementationColumn)
    description: str | None
    visibility: DataStoreVisibility = Field(
        default=DataStoreVisibility.PUBLIC,
        index=True,
        description="Whether the datastore appears in the catalogue callers choose from.",
    )
    creation_date: datetime = Field(default_factory=datetime.now)
