"""Tests of the privilege boundary a table is queried behind.

This is the security core of tables, so it is tested against a real SQLite
database rather than through a stub. What is being pinned down is that the
boundary is the *engine's*: the platform hands SQLite a statement it has
never read, on a connection that cannot do more than the caller may, and
SQLite is what refuses the rest.

There are two boundaries, and they fail differently on purpose:

- Another project's table is in another namespace, which for SQLite is a
  different file. It is not refused, it is simply not there, so a statement
  reaching for it fails the way a statement naming any absent table fails and
  learns nothing about whether it exists.
- Another table in the caller's *own* namespace is right there in the same
  file, and is refused by the authorizer.

These tests need no policy engine, so they run whether or not `opa` is
installed.
"""

from pathlib import Path

import pytest

from src.features.datastores.model import SQLiteDataStore
from src.features.datastores.storage import DataStoreQuery
from src.features.tables.storage import ColumnDefinition, QueryPrivilege, TableStorage
from src.platform.exceptions import QueryFailedError, QueryRefusedError, TableProvisioningError

#: Two projects' corners of the same datastore.
OURS = "pours"
THEIRS = "ptheirs"

#: The table under test, a second table beside it, and another project's.
TABLE = "records"
SIBLING = "notes"


@pytest.fixture
def store(tmp_path: Path) -> SQLiteDataStore:
    """Return a SQLite datastore backed by a throwaway file.

    Args:
        tmp_path: Directory unique to the running test.

    Returns:
        SQLiteDataStore: A datastore holding nothing yet.
    """
    return SQLiteDataStore(sqlite_connection_string=str(tmp_path / "warehouse.db"))


@pytest.fixture
async def populated(store: SQLiteDataStore) -> SQLiteDataStore:
    """Return a datastore holding our two tables and another project's.

    Both projects name a table `records`, which is the arrangement namespaces
    exist to make safe.

    Args:
        store: The empty datastore.

    Returns:
        SQLiteDataStore: The datastore, with every table created and filled.
    """
    for namespace, table, value in (
        (OURS, TABLE, "ours"),
        (OURS, SIBLING, "our note"),
        (THEIRS, TABLE, "theirs"),
    ):
        await store.create_table(
            namespace=namespace,
            name=table,
            columns=[
                ColumnDefinition(name="id", type="INTEGER", nullable=False),
                ColumnDefinition(name="note", type="VARCHAR(255)"),
            ],
        )
        await store.query_table(
            namespace=namespace,
            name=table,
            query=DataStoreQuery(query=f"INSERT INTO {table} VALUES (1, '{value}')"),
            privilege=QueryPrivilege.READ_WRITE,
        )

    return store


async def _run(
    *,
    store: SQLiteDataStore,
    sql: str,
    privilege: QueryPrivilege = QueryPrivilege.READ_WRITE,
    namespace: str = OURS,
) -> list:
    """Run `sql` against our table at `privilege` and return the rows.

    Args:
        store: The datastore holding the table.
        sql: The statement to run.
        privilege: The most the statement may do.
        namespace: The project whose corner of the datastore to use.

    Returns:
        list: The rows the statement produced.
    """
    response = await store.query_table(
        namespace=namespace,
        name=TABLE,
        query=DataStoreQuery(query=sql),
        privilege=privilege,
    )
    return response.data


def test_the_sqlite_implementation_offers_table_storage(store: SQLiteDataStore) -> None:
    """The service layer decides what a datastore can do by asking this."""
    assert isinstance(store, TableStorage)


async def test_a_table_is_created_with_the_columns_asked_for(
    store: SQLiteDataStore,
) -> None:
    """Creating a table is the platform's job, done at its own privilege."""
    await store.create_table(
        namespace=OURS,
        name=TABLE,
        columns=[
            ColumnDefinition(name="id", type="INTEGER", nullable=False),
            ColumnDefinition(name="note", type="TEXT"),
        ],
    )

    response = await store.query_table(
        namespace=OURS,
        name=TABLE,
        query=DataStoreQuery(query=f"SELECT id, note FROM {TABLE}"),
        privilege=QueryPrivilege.READ_ONLY,
    )

    assert response.metadata["columns"] == ["id", "note"]


async def test_a_table_must_have_at_least_one_column(store: SQLiteDataStore) -> None:
    """A table with no columns is not a table."""
    with pytest.raises(TableProvisioningError):
        await store.create_table(namespace=OURS, name=TABLE, columns=[])


async def test_a_namespace_that_is_not_a_plain_name_is_refused(
    store: SQLiteDataStore,
) -> None:
    """A namespace picks a file, so it must not be able to pick any file."""
    with pytest.raises(TableProvisioningError):
        await store.create_table(
            namespace="../../etc/passwd",
            name=TABLE,
            columns=[ColumnDefinition(name="id", type="INTEGER")],
        )


# --- the privilege levels -----------------------------------------------------


async def test_a_read_only_caller_may_select(populated: SQLiteDataStore) -> None:
    """The lowest privilege still reaches the rows."""
    rows = await _run(
        store=populated,
        sql=f"SELECT * FROM {TABLE}",
        privilege=QueryPrivilege.READ_ONLY,
    )

    assert rows == [(1, "ours")]


@pytest.mark.parametrize(
    "statement",
    [
        f"INSERT INTO {TABLE} VALUES (2, 'no')",
        f"UPDATE {TABLE} SET note = 'no'",
        f"DELETE FROM {TABLE}",
        f"ALTER TABLE {TABLE} ADD COLUMN extra TEXT",
    ],
)
async def test_a_read_only_caller_may_change_nothing(
    populated: SQLiteDataStore, statement: str
) -> None:
    """Read-only means it, for rows and for the shape of the table alike.

    Args:
        populated: The datastore holding every table.
        statement: A statement that would change something.
    """
    with pytest.raises(QueryRefusedError):
        await _run(store=populated, sql=statement, privilege=QueryPrivilege.READ_ONLY)


async def test_a_read_write_caller_may_change_rows(populated: SQLiteDataStore) -> None:
    """Writing is what the higher privilege adds."""
    await _run(store=populated, sql=f"INSERT INTO {TABLE} VALUES (2, 'added')")

    rows = await _run(
        store=populated,
        sql=f"SELECT note FROM {TABLE} ORDER BY id",
        privilege=QueryPrivilege.READ_ONLY,
    )
    assert rows == [("ours",), ("added",)]


async def test_a_read_write_caller_may_alter_the_table(
    populated: SQLiteDataStore,
) -> None:
    """DDL that shapes the caller's own table is allowed.

    This is the case that breaks if the authorizer refuses SQLite's own reads
    and writes of `sqlite_master`, which `ALTER TABLE` performs on the
    caller's behalf.
    """
    await _run(store=populated, sql=f"ALTER TABLE {TABLE} ADD COLUMN extra TEXT")

    response = await populated.query_table(
        namespace=OURS,
        name=TABLE,
        query=DataStoreQuery(query=f"SELECT * FROM {TABLE}"),
        privilege=QueryPrivilege.READ_ONLY,
    )
    assert response.metadata["columns"] == ["id", "note", "extra"]


# --- what nobody may do -------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE smuggled (x INTEGER)",
        f"CREATE VIEW peek AS SELECT * FROM {TABLE}",
        f"CREATE INDEX i ON {TABLE} (id)",
        f"CREATE TRIGGER t AFTER INSERT ON {TABLE} BEGIN SELECT 1; END",
    ],
)
async def test_nobody_may_create_anything(
    populated: SQLiteDataStore, statement: str
) -> None:
    """Creating is the platform's privilege, and is never lent out.

    Args:
        populated: The datastore holding every table.
        statement: A statement that would create something.
    """
    with pytest.raises(QueryRefusedError):
        await _run(store=populated, sql=statement)


@pytest.mark.parametrize("target", [TABLE, SIBLING])
async def test_nobody_may_drop_a_table(populated: SQLiteDataStore, target: str) -> None:
    """Not even their own: dropping is how the platform loses track of a table.

    Args:
        populated: The datastore holding every table.
        target: The table the statement tries to drop.
    """
    with pytest.raises(QueryRefusedError):
        await _run(store=populated, sql=f"DROP TABLE {target}")

    survived = await populated.query_table(
        namespace=OURS,
        name=target,
        query=DataStoreQuery(query=f"SELECT count(*) FROM {target}"),
        privilege=QueryPrivilege.READ_ONLY,
    )
    assert survived.data == [(1,)]


@pytest.mark.parametrize(
    "statement",
    [
        "ATTACH DATABASE 'elsewhere.db' AS elsewhere",
        f"PRAGMA table_info({TABLE})",
        "ANALYZE",
        "VACUUM",
    ],
)
async def test_the_ways_around_the_boundary_are_shut(
    populated: SQLiteDataStore, statement: str
) -> None:
    """Reaching another database, or the machinery, is refused as well.

    Note that a statement with nothing to act on, such as `REINDEX` against a
    database that has no indexes, asks SQLite's authorizer nothing at all and
    so is neither allowed nor refused - it simply does nothing.

    Args:
        populated: The datastore holding every table.
        statement: A statement that would step outside the table.
    """
    with pytest.raises(QueryRefusedError):
        await _run(store=populated, sql=statement)


async def test_the_schema_is_hidden_from_a_read_only_caller(
    populated: SQLiteDataStore,
) -> None:
    """A caller who cannot alter has no reason to read the catalogue."""
    with pytest.raises(QueryRefusedError):
        await _run(
            store=populated,
            sql="SELECT name FROM sqlite_master",
            privilege=QueryPrivilege.READ_ONLY,
        )


async def test_a_second_statement_cannot_ride_along(
    populated: SQLiteDataStore,
) -> None:
    """Hiding a drop behind a harmless select does not work."""
    with pytest.raises(QueryFailedError):
        await _run(store=populated, sql=f"SELECT 1; DROP TABLE {TABLE}")


async def test_a_broken_statement_is_a_failure_and_not_a_refusal(
    populated: SQLiteDataStore,
) -> None:
    """The two are told apart, so the caller learns which of the two happened."""
    with pytest.raises(QueryFailedError):
        await _run(store=populated, sql="SELECT FROM WHERE")


# --- the two boundaries -------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        f"SELECT * FROM {SIBLING}",
        f"SELECT * FROM {TABLE}, {SIBLING}",
        f"SELECT (SELECT note FROM {SIBLING})",
        f"WITH borrowed AS (SELECT * FROM {SIBLING}) SELECT * FROM borrowed",
        f"INSERT INTO {SIBLING} VALUES (2, 'no')",
        f"UPDATE {SIBLING} SET note = 'no'",
        f"DELETE FROM {SIBLING}",
        f"ALTER TABLE {SIBLING} ADD COLUMN extra TEXT",
    ],
)
async def test_a_statement_stops_at_the_table_it_was_given(
    populated: SQLiteDataStore, statement: str
) -> None:
    """One statement reaches one table, however many it names.

    The sibling here belongs to the same project and sits in the same file, so
    only the authorizer stands between them. Joins, subqueries and common
    table expressions are all ways of naming a second table in one statement,
    which is what a check over statement text would have to catch every
    spelling of.

    Args:
        populated: The datastore holding every table.
        statement: A statement reaching for the table beside this one.
    """
    with pytest.raises(QueryRefusedError):
        await _run(store=populated, sql=statement)


async def test_two_projects_may_hold_a_table_of_the_same_name(
    populated: SQLiteDataStore,
) -> None:
    """The same name in two namespaces is two tables, and each sees its own."""
    ours = await _run(store=populated, sql=f"SELECT note FROM {TABLE}", namespace=OURS)
    theirs = await _run(
        store=populated, sql=f"SELECT note FROM {TABLE}", namespace=THEIRS
    )

    assert ours == [("ours",)]
    assert theirs == [("theirs",)]


async def test_another_projects_table_is_not_even_visible(
    populated: SQLiteDataStore,
) -> None:
    """Namespaces put other projects out of reach rather than out of bounds.

    The sibling table above is refused because it is there and forbidden. This
    one is in another project's namespace, so it is not there at all, and the
    caller cannot tell from the answer whether it ever was.
    """
    with pytest.raises(QueryFailedError) as failure:
        await _run(store=populated, sql=f"SELECT * FROM {SIBLING}", namespace=THEIRS)

    assert "no such table" in str(failure.value)


async def test_dropping_a_table_takes_the_data_with_it(
    populated: SQLiteDataStore,
) -> None:
    """The platform's own privilege can do what it never lends out."""
    await populated.drop_table(namespace=OURS, name=TABLE)

    with pytest.raises(QueryFailedError):
        await _run(store=populated, sql=f"SELECT * FROM {TABLE}")

    # The table beside it, and the other project's, are untouched.
    sibling = await populated.query_table(
        namespace=OURS,
        name=SIBLING,
        query=DataStoreQuery(query=f"SELECT note FROM {SIBLING}"),
        privilege=QueryPrivilege.READ_ONLY,
    )
    assert sibling.data == [("our note",)]

    assert await _run(
        store=populated, sql=f"SELECT note FROM {TABLE}", namespace=THEIRS
    ) == [("theirs",)]


# --- what may be written into DDL ---------------------------------------------


@pytest.mark.parametrize(
    "column_type",
    [
        "TEXT); DROP TABLE other; --",
        "TEXT --",
        "TEXT'",
        'TEXT"',
    ],
)
def test_a_column_type_that_could_end_the_statement_is_rejected(
    column_type: str,
) -> None:
    """Types are written by the caller and land in DDL, so they are checked.

    The platform passes the type to the engine without understanding it, which
    is only safe while the text cannot stop being a type.

    Args:
        column_type: A type that tries to be more than a type.
    """
    with pytest.raises(ValueError):
        ColumnDefinition(name="x", type=column_type)


@pytest.mark.parametrize(
    "column_type", ["INTEGER", "VARCHAR(255)", "DECIMAL(10, 2)", "TIMESTAMP WITH TIME ZONE"]
)
def test_the_types_people_actually_write_are_accepted(column_type: str) -> None:
    """The check must not cost callers the dialect they came for.

    Args:
        column_type: A type a caller would reasonably ask for.
    """
    assert ColumnDefinition(name="x", type=column_type).type == column_type


@pytest.mark.parametrize("name", ["drop table", "a-b", "1abc", "", "x" * 64])
def test_a_column_name_that_is_not_an_identifier_is_rejected(name: str) -> None:
    """Column names land in DDL too, and are never quoted for the caller.

    Args:
        name: A name that is not a plain identifier.
    """
    with pytest.raises(ValueError):
        ColumnDefinition(name=name, type="TEXT")


def _corrupt(*, directory: Path, namespace: str) -> None:
    """Replace `namespace`'s database file with something that is not one.

    The datastore names the file after the one it was configured with, so
    every candidate in the directory is overwritten rather than the name
    being guessed at here.

    Args:
        directory: The directory the datastore was pointed at.
        namespace: The namespace whose file should be made unreadable.

    Raises:
        AssertionError: If there was no file to corrupt, which would leave the
            test asserting nothing.
    """
    files = [path for path in directory.glob("*.db") if namespace in path.name]
    assert files, f"no database file for '{namespace}' to corrupt"

    for path in files:
        path.write_bytes(b"this is not a SQLite database at all")


# --- when the file itself is not usable ---------------------------------------
#
# Everything above goes wrong inside a working database. These are the failures
# of the file underneath it, which reach the platform as the same kind of error
# rather than as a `sqlite3` exception escaping into a response.


async def test_dropping_a_table_from_a_file_that_is_not_a_database_is_reported(
    store: SQLiteDataStore, tmp_path: Path
) -> None:
    """The platform's own error, so the router has something it can answer with."""
    await store.create_table(
        namespace=OURS,
        name=TABLE,
        columns=[ColumnDefinition(name="id", type="INTEGER", nullable=False)],
    )
    _corrupt(directory=tmp_path, namespace=OURS)

    with pytest.raises(TableProvisioningError, match=f"'{TABLE}' could not be dropped"):
        await store.drop_table(namespace=OURS, name=TABLE)


async def test_creating_a_table_in_a_file_that_is_not_a_database_is_reported(
    store: SQLiteDataStore, tmp_path: Path
) -> None:
    """The same failure on the way in, reported the same way.

    The project's first table is created normally, because that is what
    brings the file into being; it is the second one that meets the damage.
    """
    await store.create_table(
        namespace=OURS,
        name=TABLE,
        columns=[ColumnDefinition(name="id", type="INTEGER", nullable=False)],
    )
    _corrupt(directory=tmp_path, namespace=OURS)

    with pytest.raises(TableProvisioningError, match=f"'{SIBLING}' could not be created"):
        await store.create_table(
            namespace=OURS,
            name=SIBLING,
            columns=[ColumnDefinition(name="id", type="INTEGER", nullable=False)],
        )
