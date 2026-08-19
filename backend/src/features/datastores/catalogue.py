"""The storage a project may choose from, described without how to reach it.

A datastore is part of the platform, and only a platform administrator may
act on one. But a project has to *name* a datastore to put a table or a blob
in it, and a name nobody outside the administrators can learn is a choice
nobody can make. The catalogue is what closes that: the list of what storage
exists and what each kind of storage holds, and nothing else.

The distinction it rests on is between a datastore and the fact that one is
on offer. Registering, reading, querying and removing a datastore stay where
they were, at the system level, because each of them involves the connection
behind it. What is here involves no connection at all.

Two things make that boundary hold rather than merely intend it. An entry is
built field by field into a model of its own, so it carries what this module
names and cannot carry anything else - an implementation that grows a new
credential field tomorrow does not leak it here, because nothing copies the
implementation across. And the entry has no place to put one: there is no
endpoint, no key, and no way to reach the storage in it.

What every authenticated caller does learn is that a datastore by some name
exists, and what its description says. That is the deliberate cost of being
able to choose, and it means a datastore's name and description are read by
everybody on the platform rather than only by its administrators.

Which is why a datastore says whether it wants to be here. A private
datastore is registered on the platform without being offered by it, so an
administrator can point the platform at storage meant for their own use
without every user reading its name. That is a filter on this list and
nothing more: a private datastore is as reachable as a public one to anybody
who has its name, so it is hidden rather than protected, and only the fact
that nothing else prints the name keeps it hidden.
"""

import asyncio

from pydantic import BaseModel, Field
from sqlmodel import Session

from src.features.datastores import service as datastores_service
from src.features.datastores.model import DataStore, DataStoreVisibility
from src.features.datastores.storage import DataType

__all__ = ["DataStoreCatalogueEntry", "list_catalogue"]


class DataStoreCatalogueEntry(BaseModel):
    """One storage option, as somebody choosing between them sees it.

    This is what a project needs in order to pick: what the storage is
    called, what shape of data it holds, and what whoever registered it said
    it was for. Everything a datastore also has - its implementation, its
    endpoint, its credential - is absent by construction rather than by
    redaction, because this model is built from a `DataStore` rather than
    derived from one.
    """

    name: str = Field(
        description="The name to give as `datastore` when creating a table or a blob.",
        examples=["objects"],
    )
    data_type: DataType = Field(
        description=(
            "The shape of data this storage holds. A blob may only be put in "
            "a `blob` store, and a table only in a `table` store."
        ),
    )
    description: str | None = Field(
        default=None,
        description="What whoever registered the datastore said it was for.",
    )


async def _describe(*, store: DataStore) -> DataStoreCatalogueEntry:
    """Describe `store` as an option rather than as a datastore.

    Args:
        store: The datastore to describe.

    Returns:
        DataStoreCatalogueEntry: The store's name, what it holds, and what it
            is for.
    """
    return DataStoreCatalogueEntry(
        name=store.name,
        data_type=await store.implementation.get_data_type(),
        description=store.description,
    )


async def list_catalogue(
    *, session: Session, data_type: DataType | None = None
) -> list[DataStoreCatalogueEntry]:
    """Return the storage on offer, optionally only what holds `data_type`.

    Only public datastores are on offer. A private one is left out of the
    answer entirely rather than named and refused, because a name is the whole
    of what this endpoint gives away and half of it would give away all of it.

    Filtering by shape here rather than leaving it to the caller is what makes
    the answer usable: somebody about to create a blob wants the stores a blob
    may go in, and a list they have to sift is a list they can pick wrongly
    from.

    Args:
        session: The open database session.
        data_type: If given, only storage holding data of this shape.

    Returns:
        list[DataStoreCatalogueEntry]: The storage a project may choose from.
    """
    stores = datastores_service.list_datastores(
        session=session, visibility=DataStoreVisibility.PUBLIC
    )
    entries = await asyncio.gather(
        *(_describe(store=store) for store in stores)
    )

    if data_type is None:
        return list(entries)

    return [entry for entry in entries if entry.data_type is data_type]
