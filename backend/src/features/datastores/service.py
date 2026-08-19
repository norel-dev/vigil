"""Reading, writing and querying datastores.

The endpoints in front of this module decide *whether* a caller may touch a
datastore; this module knows *how* to reach it.
"""

from sqlmodel import Session, select

from src.features.datastores.model import (
    DataStore,
    DataStoreImplementations,
    DataStoreVisibility,
)
from src.features.datastores.storage import DataStoreQuery, DataStoreQueryResponse
from src.platform.exceptions import ObjectNotFoundError

__all__ = [
    "create_datastore",
    "delete_datastore",
    "get_datastore",
    "list_datastores",
    "run_query",
    "set_visibility",
]


def create_datastore(
    *,
    session: Session,
    name: str,
    description: str | None,
    implementation: DataStoreImplementations,
    visibility: DataStoreVisibility = DataStoreVisibility.PUBLIC,
) -> DataStore:
    """Store the metadata of a new datastore.

    Args:
        session: The open database session.
        name: Name callers will refer to the datastore by.
        description: Optional description of the datastore.
        implementation: The connection details of the underlying storage.
        visibility: Whether the datastore is offered in the catalogue. Public
            by default, because registering storage the platform can be built
            on is normally an offer to build on it.

    Returns:
        DataStore: The stored datastore.
    """
    store = DataStore(
        name=name,
        description=description,
        implementation=implementation,
        visibility=visibility,
    )
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


def get_datastore(*, session: Session, name: str) -> DataStore:
    """Return the datastore called `name`.

    Args:
        session: The open database session.
        name: Name of the datastore.

    Returns:
        DataStore: The stored datastore.

    Raises:
        ObjectNotFoundError: If no datastore has that name.
    """
    store = session.get(DataStore, name)
    if store is None:
        raise ObjectNotFoundError(object_type="datastore", identifier=name)

    return store


def list_datastores(
    *, session: Session, visibility: DataStoreVisibility | None = None
) -> list[DataStore]:
    """Return the datastores in the platform, optionally only the visible ones.

    The result is not filtered by access: that is the policy's job, and the
    caller is expected to run the result past it. `visibility` is a different
    question from access and is answered here, because it is a column and the
    database is what can narrow on one without loading the rest.

    Args:
        session: The open database session.
        visibility: If given, only datastores registered with this visibility.

    Returns:
        list[DataStore]: The matching datastores.
    """
    statement = select(DataStore)
    if visibility is not None:
        statement = statement.where(DataStore.visibility == visibility)

    return list(session.exec(statement).all())


def set_visibility(
    *, session: Session, store: DataStore, visibility: DataStoreVisibility
) -> DataStore:
    """Offer `store` in the catalogue, or stop offering it.

    Nothing about the storage changes, and neither does anybody's access to
    it: a datastore that becomes private stays reachable by whoever already
    knows its name.

    Args:
        session: The open database session.
        store: The datastore to publish or unpublish.
        visibility: The visibility it should have from now on.

    Returns:
        DataStore: The updated datastore.
    """
    store.visibility = visibility
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


def delete_datastore(*, session: Session, store: DataStore) -> None:
    """Forget the metadata of `store`.

    The underlying storage is left untouched; only the platform's record of
    how to reach it is removed.

    Args:
        session: The open database session.
        store: The datastore to forget.
    """
    session.delete(store)
    session.commit()


async def run_query(*, store: DataStore, query: str) -> DataStoreQueryResponse:
    """Run `query` against the storage behind `store`.

    Args:
        store: The datastore to query.
        query: The query, in whatever dialect the implementation speaks.

    Returns:
        DataStoreQueryResponse: The rows, metadata and latency of the query.
    """
    return await store.implementation.query(query=DataStoreQuery(query=query))
