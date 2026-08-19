"""Reading, writing and querying the tables a project holds.

The endpoints in front of this module decide *whether* a caller may touch a
table; this module knows *how* to reach it, and is the only place that knows
a table has a life outside the platform's database. Every function here that
touches data does so through the `TableStorage` protocol, so nothing in it
mentions SQLite or any other engine.

Two orderings in this module are deliberate, because both halves of a table -
the storage that holds it and the record that describes it - can fail
independently:

- Creating provisions the storage first and records it second, undoing the
  provisioning if the record cannot be written. A table nobody knows about is
  worse than a create that failed, because nothing would ever clean it up.
- Deleting destroys the storage first and forgets the record second. If the
  drop fails the record survives, which keeps the platform describing
  something that really is still there.
"""

from uuid import UUID

from loguru import logger
from sqlmodel import Session, select

from src.features.datastores import service as datastores_service
from src.features.datastores.storage import (
    DataStoreQuery,
    DataStoreQueryResponse,
    DataType,
    namespace_of,
)
from src.features.tables.model import Table
from src.features.tables.storage import (
    ColumnDefinition,
    QueryPrivilege,
    TableStorage,
    validate_identifier,
)
from src.platform.exceptions import (
    DuplicateObjectError,
    ObjectNotFoundError,
    UnsuitableDataStoreError,
)

__all__ = [
    "create_table",
    "delete_table",
    "get_table",
    "list_tables",
    "namespace_of",
    "run_query",
]


async def _storage_behind(*, session: Session, datastore_name: str) -> TableStorage:
    """Return the table storage of the datastore called `datastore_name`.

    Args:
        session: The open database session.
        datastore_name: Name of the datastore to reach.

    Returns:
        TableStorage: The datastore's implementation, as table storage.

    Raises:
        ObjectNotFoundError: If no datastore has that name.
        UnsuitableDataStoreError: If that datastore does not hold tables.
    """
    store = datastores_service.get_datastore(session=session, name=datastore_name)
    implementation = store.implementation

    # Both halves of this matter. The data type is what the platform promises
    # its users - a table goes in a datastore of type table - while the
    # protocol is whether the implementation can actually carry that out.
    holds_tables = await implementation.get_data_type() is DataType.TABLE
    if not holds_tables or not isinstance(implementation, TableStorage):
        raise UnsuitableDataStoreError(datastore=store.name, wanted="tables")

    return implementation


def get_table(*, session: Session, project_id: UUID, name: str) -> Table:
    """Return the table `name` belonging to `project_id`.

    Args:
        session: The open database session.
        project_id: The project the table belongs to.
        name: What the project calls the table.

    Returns:
        Table: The stored table.

    Raises:
        ObjectNotFoundError: If that project has no table with that name.
    """
    table = session.exec(
        select(Table).where(Table.project_id == project_id, Table.name == name)
    ).first()

    if table is None:
        raise ObjectNotFoundError(object_type="table", identifier=name)

    return table


def list_tables(*, session: Session, project_id: UUID) -> list[Table]:
    """Return every table belonging to `project_id`.

    The result is not filtered by access: that is the policy's job, and the
    caller is expected to run the result past it.

    Args:
        session: The open database session.
        project_id: The project whose tables to list.

    Returns:
        list[Table]: The project's tables.
    """
    return list(session.exec(select(Table).where(Table.project_id == project_id)).all())


async def create_table(
    *,
    session: Session,
    project_id: UUID,
    datastore_name: str,
    name: str,
    description: str | None,
    columns: list[ColumnDefinition],
) -> Table:
    """Create a table in a datastore and record that the project holds it.

    Args:
        session: The open database session.
        project_id: The project the table will belong to.
        datastore_name: Name of the datastore that will hold it.
        name: What the project will call the table.
        description: Optional description of the table.
        columns: The columns the table should have, in order.

    Returns:
        Table: The stored table.

    Raises:
        ObjectNotFoundError: If the datastore does not exist.
        UnsuitableDataStoreError: If the datastore does not hold tables.
        DuplicateObjectError: If the project already has a table with that name.
        ValueError: If the name is not usable as a SQL identifier.
        TableProvisioningError: If the storage could not be created.
    """
    # The name the caller picks is the name they will write in their SQL, so
    # it has to be a name SQL can take.
    validate_identifier(name=name, kind="table name")

    storage = await _storage_behind(session=session, datastore_name=datastore_name)

    already_there = session.exec(
        select(Table).where(Table.project_id == project_id, Table.name == name)
    ).first()
    if already_there is not None:
        raise DuplicateObjectError(object_type="table", identifier=name)

    namespace = namespace_of(project_id=project_id)
    await storage.create_table(namespace=namespace, name=name, columns=columns)

    table = Table(
        name=name,
        project_id=project_id,
        datastore_name=datastore_name,
        description=description,
    )

    try:
        session.add(table)
        session.commit()
        session.refresh(table)
    except Exception:
        # The storage exists but nothing now points at it, so take it back
        # out rather than leaving a table nobody can name or ever delete.
        session.rollback()
        logger.error(
            "Recording the table '{}' failed after it was created in {}; "
            "removing it again",
            name,
            datastore_name,
        )
        await storage.drop_table(namespace=namespace, name=name)
        raise

    return table


async def delete_table(*, session: Session, table: Table) -> None:
    """Destroy a table's data and forget that the project held it.

    Args:
        session: The open database session.
        table: The table to destroy.

    Raises:
        ObjectNotFoundError: If the datastore behind the table is gone.
        UnsuitableDataStoreError: If that datastore does not hold tables.
        TableProvisioningError: If the storage could not be dropped, in which
            case the platform's record of the table is kept.
    """
    storage = await _storage_behind(session=session, datastore_name=table.datastore_name)

    await storage.drop_table(
        namespace=namespace_of(project_id=table.project_id), name=table.name
    )
    session.delete(table)
    session.commit()


async def run_query(
    *,
    session: Session,
    table: Table,
    query: str,
    privilege: QueryPrivilege,
) -> DataStoreQueryResponse:
    """Run `query` against `table`, at no more than `privilege`.

    The statement is not read here, nor anywhere else in the platform. It is
    handed to the storage together with the privilege the caller earned, and
    the engine is what refuses anything beyond it.

    Args:
        session: The open database session.
        table: The table to query.
        query: The statement, in the dialect the datastore speaks.
        privilege: The most the statement is allowed to do.

    Returns:
        DataStoreQueryResponse: The rows, metadata and latency of the query.

    Raises:
        ObjectNotFoundError: If the datastore behind the table is gone.
        UnsuitableDataStoreError: If that datastore does not hold tables.
        QueryRefusedError: If the engine refused the statement.
        QueryFailedError: If the statement was allowed but did not run.
    """
    storage = await _storage_behind(session=session, datastore_name=table.datastore_name)

    return await storage.query_table(
        namespace=namespace_of(project_id=table.project_id),
        name=table.name,
        query=DataStoreQuery(query=query),
        privilege=privilege,
    )
