"""End to end tests of who may do what to a project's tables.

These go through the real application and the real policy engine, so what
they pin down is the whole path: the role a caller holds becomes a policy
decision, the decision becomes the privilege the platform connects to the
datastore with, and the database engine enforces it.

The case worth reading first is
`test_two_projects_sharing_a_datastore_never_see_each_other`. Two projects
share one datastore and each name a table the same thing, which is the
arrangement the platform exists to make safe.
"""

import sqlite3
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from src.features.tables import service as tables_service
from src.features.tables.storage import ColumnDefinition
from tests.conftest import headers_for, make_platform_admin

#: The columns most of these tests create their table with.
COLUMNS = [
    {"name": "id", "type": "INTEGER", "nullable": False},
    {"name": "note", "type": "TEXT", "nullable": True},
]


def _tables_held_by(*, datastore_path: Path) -> set[str]:
    """Return every table in every file the datastore at `datastore_path` made.

    A SQLite datastore gives each project a file of its own beside the one it
    was configured with, named after it, so those are the files to look in -
    and only those. The platform's own metadata database lives in the same
    directory and is full of tables that have nothing to do with any project.

    Args:
        datastore_path: The file the datastore was configured with.

    Returns:
        set[str]: The names of the tables found.

    Raises:
        AssertionError: If the datastore made no file at all, which would
            leave the caller asserting against nothing.
    """
    companions = sorted(
        datastore_path.parent.glob(f"{datastore_path.stem}__*{datastore_path.suffix}")
    )
    assert companions, f"the datastore at {datastore_path} made no file to inspect"

    found: set[str] = set()
    for database in companions:
        with sqlite3.connect(database) as connection:
            found.update(
                name
                for (name,) in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            )

    return found


def _register_datastore(
    *, client: TestClient, session: Session, path: Path, name: str = "warehouse"
) -> str:
    """Register a SQLite datastore, which only a platform administrator may do.

    Args:
        client: The test client.
        session: A session on the test database, used to promote the caller.
        path: Where the datastore's SQLite file should live.
        name: Name to register the datastore under.

    Returns:
        str: The name of the registered datastore.
    """
    make_platform_admin(session=session, email="root@example.com")

    response = client.post(
        "/datastores/",
        json={
            "name": name,
            "description": "storage for the tests",
            "datastore": {
                "implementation": "sqlite",
                "sqlite_connection_string": str(path),
            },
        },
        headers=headers_for(caller="root"),
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    return name


def _create_project(*, client: TestClient, caller: str, name: str) -> str:
    """Create a project owned by `caller` and return its id.

    Args:
        client: The test client.
        caller: The name of the caller creating it.
        name: Name of the new project.

    Returns:
        str: The id of the created project.
    """
    response = client.post(
        "/projects/",
        json={"name": name, "description": None},
        headers=headers_for(caller=caller),
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    return str(response.json()["id"])


def _create_table(
    *,
    client: TestClient,
    caller: str,
    project_id: str,
    datastore: str,
    name: str = "records",
    columns: list[dict] | None = None,
) -> httpx.Response:
    """Ask for a table to be created, and return the raw response.

    Args:
        client: The test client.
        caller: The name of the caller.
        project_id: The project the table belongs to.
        datastore: Name of the datastore that should hold it.
        name: What the project calls the table.
        columns: The columns to create, defaulting to `COLUMNS`.

    Returns:
        httpx.Response: Whatever the API answered.
    """
    return client.post(
        f"/projects/{project_id}/tables/",
        json={
            "name": name,
            "datastore": datastore,
            "columns": COLUMNS if columns is None else columns,
            "description": None,
        },
        headers=headers_for(caller=caller),
    )


def _query(
    *,
    client: TestClient,
    caller: str,
    project_id: str,
    table: str,
    sql: str,
) -> httpx.Response:
    """Run a statement against a table and return the raw response.

    Args:
        client: The test client.
        caller: The name of the caller.
        project_id: The project the table belongs to.
        table: What the project calls the table.
        sql: The statement to run.

    Returns:
        httpx.Response: Whatever the API answered.
    """
    return client.post(
        f"/projects/{project_id}/tables/{table}/query",
        json={"query": sql},
        headers=headers_for(caller=caller),
    )


def _grant(
    *, client: TestClient, owner: str, project_id: str, email: str, role: str
) -> None:
    """Give `email` the role `role` in `project_id`.

    Args:
        client: The test client.
        owner: The name of somebody who may manage its members.
        project_id: The project to grant access to.
        email: Address of the user being let in.
        role: The role to grant.
    """
    response = client.put(
        f"/projects/{project_id}/members",
        json={"email": email, "role": role},
        headers=headers_for(caller=owner),
    )
    assert response.status_code == httpx.codes.OK, response.text


@pytest.fixture
def warehouse(client: TestClient, session: Session, tmp_path: Path) -> str:
    """Return the name of a registered datastore that holds tables.

    Args:
        client: The test client.
        session: A session on the test database.
        tmp_path: Directory unique to the running test.

    Returns:
        str: The datastore's name.
    """
    return _register_datastore(
        client=client, session=session, path=tmp_path / "warehouse.db"
    )


@pytest.fixture
def alices_table(client: TestClient, warehouse: str) -> tuple[str, str]:
    """Return a project owned by Alice, holding one table with a row in it.

    Args:
        client: The test client.
        warehouse: The datastore that will hold the table.

    Returns:
        tuple[str, str]: The project id and the table's name.
    """
    project_id = _create_project(client=client, caller="alice", name="alices project")
    created = _create_table(
        client=client, caller="alice", project_id=project_id, datastore=warehouse
    )
    assert created.status_code == httpx.codes.CREATED, created.text

    inserted = _query(
        client=client,
        caller="alice",
        project_id=project_id,
        table="records",
        sql="INSERT INTO records VALUES (1, 'alices row')",
    )
    assert inserted.status_code == httpx.codes.OK, inserted.text
    return project_id, "records"


# --- creating -----------------------------------------------------------------


def test_an_owner_creates_a_table_and_reads_it_back(
    client: TestClient, warehouse: str
) -> None:
    """The straightforward path: a project owner claims some storage."""
    project_id = _create_project(client=client, caller="alice", name="alices project")

    created = _create_table(
        client=client, caller="alice", project_id=project_id, datastore=warehouse
    )

    assert created.status_code == httpx.codes.CREATED, created.text
    body = created.json()
    assert body["name"] == "records"
    assert body["datastore_name"] == warehouse

    read_back = client.get(
        f"/projects/{project_id}/tables/records", headers=headers_for(caller="alice")
    )
    assert read_back.status_code == httpx.codes.OK, read_back.text


def test_a_datastore_holding_a_table_cannot_be_forgotten(
    client: TestClient, warehouse: str, alices_table: tuple[str, str]
) -> None:
    """Forgetting the datastore would leave Alice's table pointing at nothing."""
    project_id, table = alices_table

    forgotten = client.delete(f"/datastores/{warehouse}", headers=headers_for(caller="root"))

    assert forgotten.status_code == httpx.codes.CONFLICT, forgotten.text
    assert "still in use" in forgotten.json()["detail"]
    still_there = client.get(
        f"/projects/{project_id}/tables/{table}", headers=headers_for(caller="alice")
    )
    assert still_there.status_code == httpx.codes.OK, still_there.text


def test_a_table_cannot_be_created_in_a_datastore_that_holds_blobs(
    client: TestClient, session: Session, warehouse: str
) -> None:
    """A store is checked for what it holds before anything is asked of it.

    The store named here is never reached - it is registered against an
    endpoint nothing is listening on - because the platform turns the request
    down on what the datastore *is* rather than on what it answers.
    `test_blob_access.py` covers the same refusal the other way round.
    """
    make_platform_admin(session=session, email="root@example.com")
    registered = client.post(
        "/datastores/",
        json={
            "name": "objects",
            "description": "blobs, not tables",
            "datastore": {
                "implementation": "minio",
                "endpoint": "127.0.0.1:1",
                "access_key": "unused",
                "secret_key": "unused",
                "secure": False,
            },
        },
        headers=headers_for(caller="root"),
    )
    assert registered.status_code == httpx.codes.CREATED, registered.text

    project_id = _create_project(client=client, caller="alice", name="alices project")
    created = _create_table(
        client=client, caller="alice", project_id=project_id, datastore="objects"
    )

    assert created.status_code == httpx.codes.BAD_REQUEST, created.text
    assert "does not hold tables" in created.text


def test_a_table_with_no_columns_is_refused(client: TestClient, warehouse: str) -> None:
    """There is no such thing as a table with nothing in it."""
    project_id = _create_project(client=client, caller="alice", name="alices project")

    created = _create_table(
        client=client,
        caller="alice",
        project_id=project_id,
        datastore=warehouse,
        columns=[],
    )

    assert created.status_code in {
        httpx.codes.BAD_REQUEST,
        httpx.codes.UNPROCESSABLE_ENTITY,
    }, created.text


def test_a_key_column_that_may_hold_no_value_is_refused_at_the_door(
    client: TestClient, warehouse: str
) -> None:
    """A caller who contradicted themselves is told so, not quietly obeyed.

    Unlike a column type, this is not something only the engine can judge:
    SQLite would take the table and then allow NULLs in its key, so the
    platform refuses the request rather than creating a table that is not the
    one that was asked for.
    """
    project_id = _create_project(client=client, caller="alice", name="alices project")

    created = _create_table(
        client=client,
        caller="alice",
        project_id=project_id,
        datastore=warehouse,
        columns=[{"name": "id", "type": "INTEGER", "nullable": True, "primary_key": True}],
    )

    assert created.status_code == httpx.codes.UNPROCESSABLE_ENTITY, created.text
    assert "must hold a value" in created.text


def test_a_table_is_created_with_the_key_its_columns_asked_for(
    client: TestClient, warehouse: str
) -> None:
    """The key reaches the engine, which then holds the table to it."""
    project_id = _create_project(client=client, caller="alice", name="alices project")

    created = _create_table(
        client=client,
        caller="alice",
        project_id=project_id,
        datastore=warehouse,
        columns=[
            {"name": "id", "type": "INTEGER", "nullable": False, "primary_key": True},
            {"name": "note", "type": "TEXT", "nullable": True},
        ],
    )
    assert created.status_code == httpx.codes.CREATED, created.text

    first = _query(
        client=client,
        caller="alice",
        project_id=project_id,
        table="records",
        sql="INSERT INTO records VALUES (1, 'first')",
    )
    assert first.status_code == httpx.codes.OK, first.text

    again = _query(
        client=client,
        caller="alice",
        project_id=project_id,
        table="records",
        sql="INSERT INTO records VALUES (1, 'again')",
    )
    assert again.status_code == httpx.codes.BAD_REQUEST, again.text


def test_a_column_the_engine_will_not_accept_is_answered_with_a_400(
    client: TestClient, warehouse: str
) -> None:
    """The platform does not read column types, so the engine's refusal is passed on.

    A type the platform invented a rule for would be a type SQLite might
    accept and the platform would not, so what it does instead is hand the
    definition over and report back what came of it. That makes this the
    caller's mistake - a 400 - rather than the platform's.
    """
    project_id = _create_project(client=client, caller="alice", name="alices project")

    created = _create_table(
        client=client,
        caller="alice",
        project_id=project_id,
        datastore=warehouse,
        columns=[{"name": "id", "type": "NOT A TYPE", "nullable": False}],
    )

    assert created.status_code == httpx.codes.BAD_REQUEST, created.text


def test_nothing_is_recorded_when_the_storage_could_not_be_shaped(
    client: TestClient, warehouse: str
) -> None:
    """A table that failed to be created is not one the project now has.

    Recording it anyway would leave the project holding the name of a table
    that is not there, which it could then neither use nor create again.
    """
    project_id = _create_project(client=client, caller="alice", name="alices project")
    _create_table(
        client=client,
        caller="alice",
        project_id=project_id,
        datastore=warehouse,
        name="doomed",
        columns=[{"name": "id", "type": "NOT A TYPE", "nullable": False}],
    )

    listed = client.get(
        f"/projects/{project_id}/tables/", headers=headers_for(caller="alice")
    )
    assert listed.status_code == httpx.codes.OK, listed.text
    assert [table["name"] for table in listed.json()] == []

    # And the name is still free, which is the thing a stale record would cost.
    retried = _create_table(
        client=client,
        caller="alice",
        project_id=project_id,
        datastore=warehouse,
        name="doomed",
    )
    assert retried.status_code == httpx.codes.CREATED, retried.text


def test_a_table_cannot_be_created_in_a_datastore_that_does_not_exist(
    client: TestClient, warehouse: str
) -> None:
    """A table has to live somewhere real."""
    project_id = _create_project(client=client, caller="alice", name="alices project")

    created = _create_table(
        client=client, caller="alice", project_id=project_id, datastore="imaginary"
    )

    assert created.status_code == httpx.codes.NOT_FOUND, created.text


def test_one_project_cannot_use_a_name_twice(
    client: TestClient, alices_table: tuple[str, str]
) -> None:
    """A project names its own tables, and a name means one table."""
    project_id, _ = alices_table

    again = _create_table(
        client=client, caller="alice", project_id=project_id, datastore="warehouse"
    )

    assert again.status_code == httpx.codes.CONFLICT, again.text


def test_two_projects_may_each_have_a_table_called_the_same_thing(
    client: TestClient, warehouse: str, alices_table: tuple[str, str]
) -> None:
    """Names are the project's own, so they cannot collide between projects."""
    bobs_project = _create_project(client=client, caller="bob", name="bobs project")

    created = _create_table(
        client=client, caller="bob", project_id=bobs_project, datastore=warehouse
    )

    assert created.status_code == httpx.codes.CREATED, created.text


# --- the role ladder ----------------------------------------------------------


def test_a_viewer_may_read_rows_but_not_write_them(
    client: TestClient, alices_table: tuple[str, str]
) -> None:
    """A viewer's privilege is read-only, and the engine is what holds it there."""
    project_id, table = alices_table
    _grant(
        client=client,
        owner="alice",
        project_id=project_id,
        email="bob@example.com",
        role="viewer",
    )

    read = _query(
        client=client,
        caller="bob",
        project_id=project_id,
        table=table,
        sql="SELECT * FROM records",
    )
    assert read.status_code == httpx.codes.OK, read.text
    assert read.json()["data"] == [[1, "alices row"]]

    write = _query(
        client=client,
        caller="bob",
        project_id=project_id,
        table=table,
        sql="INSERT INTO records VALUES (2, 'bobs row')",
    )
    assert write.status_code == httpx.codes.FORBIDDEN, write.text


def test_an_editor_may_write_rows_and_alter_the_table(
    client: TestClient, alices_table: tuple[str, str]
) -> None:
    """An editor gets the read-write privilege, which covers DML and ALTER."""
    project_id, table = alices_table
    _grant(
        client=client,
        owner="alice",
        project_id=project_id,
        email="bob@example.com",
        role="editor",
    )

    written = _query(
        client=client,
        caller="bob",
        project_id=project_id,
        table=table,
        sql="INSERT INTO records VALUES (2, 'bobs row')",
    )
    assert written.status_code == httpx.codes.OK, written.text

    altered = _query(
        client=client,
        caller="bob",
        project_id=project_id,
        table=table,
        sql="ALTER TABLE records ADD COLUMN added_at TEXT",
    )
    assert altered.status_code == httpx.codes.OK, altered.text


def test_an_editor_may_not_create_or_delete_a_table(
    client: TestClient, warehouse: str, alices_table: tuple[str, str]
) -> None:
    """Claiming and destroying storage stays with the project's owner."""
    project_id, table = alices_table
    _grant(
        client=client,
        owner="alice",
        project_id=project_id,
        email="bob@example.com",
        role="editor",
    )

    created = _create_table(
        client=client,
        caller="bob",
        project_id=project_id,
        datastore=warehouse,
        name="bobs_own",
    )
    assert created.status_code == httpx.codes.FORBIDDEN, created.text

    deleted = client.delete(
        f"/projects/{project_id}/tables/{table}", headers=headers_for(caller="bob")
    )
    assert deleted.status_code == httpx.codes.FORBIDDEN, deleted.text


def test_an_outsider_reaches_nothing(
    client: TestClient, alices_table: tuple[str, str]
) -> None:
    """Somebody with no role in the project sees none of it."""
    project_id, table = alices_table

    listed = client.get(
        f"/projects/{project_id}/tables/", headers=headers_for(caller="bob")
    )
    assert listed.status_code == httpx.codes.OK, listed.text
    assert listed.json() == []

    read = client.get(
        f"/projects/{project_id}/tables/{table}", headers=headers_for(caller="bob")
    )
    assert read.status_code == httpx.codes.FORBIDDEN, read.text

    queried = _query(
        client=client,
        caller="bob",
        project_id=project_id,
        table=table,
        sql="SELECT * FROM records",
    )
    assert queried.status_code == httpx.codes.FORBIDDEN, queried.text


def test_a_platform_administrator_reaches_any_table(
    client: TestClient, alices_table: tuple[str, str]
) -> None:
    """The platform administrator bypass covers tables like everything else."""
    project_id, table = alices_table

    queried = _query(
        client=client,
        caller="root",
        project_id=project_id,
        table=table,
        sql="SELECT * FROM records",
    )

    assert queried.status_code == httpx.codes.OK, queried.text


# --- the boundary itself ------------------------------------------------------


def test_two_projects_sharing_a_datastore_never_see_each_other(
    client: TestClient, warehouse: str, alices_table: tuple[str, str]
) -> None:
    """The arrangement the platform exists to make safe.

    Alice and Bob both have a table called `records` in the same datastore,
    and both write the same statement against it. Each sees only their own
    rows, and neither statement had to be rewritten or inspected for that to
    hold: the two tables are in different namespaces, so `records` simply
    means a different table depending on who is asking.
    """
    alices_project, _ = alices_table

    bobs_project = _create_project(client=client, caller="bob", name="bobs project")
    created = _create_table(
        client=client, caller="bob", project_id=bobs_project, datastore=warehouse
    )
    assert created.status_code == httpx.codes.CREATED, created.text

    written = _query(
        client=client,
        caller="bob",
        project_id=bobs_project,
        table="records",
        sql="INSERT INTO records VALUES (2, 'bobs row')",
    )
    assert written.status_code == httpx.codes.OK, written.text

    hers = _query(
        client=client,
        caller="alice",
        project_id=alices_project,
        table="records",
        sql="SELECT * FROM records",
    )
    his = _query(
        client=client,
        caller="bob",
        project_id=bobs_project,
        table="records",
        sql="SELECT * FROM records",
    )

    assert hers.json()["data"] == [[1, "alices row"]]
    assert his.json()["data"] == [[2, "bobs row"]]


def test_a_member_of_one_project_cannot_query_another_projects_table(
    client: TestClient, warehouse: str, alices_table: tuple[str, str]
) -> None:
    """Reaching Alice's table through her project's own URL is refused.

    Bob has a table of his own in the same datastore, so he is not a stranger
    to the platform - he simply holds no role in Alice's project.
    """
    alices_project, table = alices_table

    bobs_project = _create_project(client=client, caller="bob", name="bobs project")
    _create_table(
        client=client, caller="bob", project_id=bobs_project, datastore=warehouse
    )

    response = _query(
        client=client,
        caller="bob",
        project_id=alices_project,
        table=table,
        sql="SELECT * FROM records",
    )

    assert response.status_code == httpx.codes.FORBIDDEN, response.text


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE smuggled (x INTEGER)",
        "DROP TABLE records",
        "ATTACH DATABASE 'elsewhere.db' AS elsewhere",
    ],
)
def test_an_owner_still_cannot_create_or_drop_through_sql(
    client: TestClient, alices_table: tuple[str, str], statement: str
) -> None:
    """Owning the table does not come with the privilege that made it.

    Creating and dropping stay with the platform so that its record of what
    exists cannot drift from what is really in the datastore.

    Args:
        client: The test client.
        alices_table: Alice's project and her table.
        statement: A statement that would create or destroy something.
    """
    project_id, table = alices_table

    response = _query(
        client=client, caller="alice", project_id=project_id, table=table, sql=statement
    )

    assert response.status_code == httpx.codes.FORBIDDEN, response.text


def test_a_broken_statement_is_answered_differently_from_a_refused_one(
    client: TestClient, alices_table: tuple[str, str]
) -> None:
    """A caller can tell 'you may not' apart from 'that did not work'."""
    project_id, table = alices_table

    response = _query(
        client=client,
        caller="alice",
        project_id=project_id,
        table=table,
        sql="SELECT nonexistent FROM records",
    )

    assert response.status_code == httpx.codes.BAD_REQUEST, response.text


# --- deleting -----------------------------------------------------------------


def test_deleting_a_table_destroys_it(
    client: TestClient, alices_table: tuple[str, str]
) -> None:
    """Deleting a table is not the same as forgetting a datastore.

    The platform created this table, so it destroys it: the record goes and
    so do the rows.
    """
    project_id, table = alices_table

    deleted = client.delete(
        f"/projects/{project_id}/tables/{table}", headers=headers_for(caller="alice")
    )
    assert deleted.status_code == httpx.codes.NO_CONTENT, deleted.text

    gone = client.get(
        f"/projects/{project_id}/tables/{table}", headers=headers_for(caller="alice")
    )
    assert gone.status_code == httpx.codes.NOT_FOUND, gone.text

    # The name is free again, and the table that comes back is empty.
    recreated = _create_table(
        client=client, caller="alice", project_id=project_id, datastore="warehouse"
    )
    assert recreated.status_code == httpx.codes.CREATED, recreated.text

    rows = _query(
        client=client,
        caller="alice",
        project_id=project_id,
        table=table,
        sql="SELECT * FROM records",
    )
    assert rows.json()["data"] == []


def test_listing_shows_a_project_only_its_own_tables(
    client: TestClient, warehouse: str, alices_table: tuple[str, str]
) -> None:
    """Sharing a datastore does not mean sharing a listing."""
    bobs_project = _create_project(client=client, caller="bob", name="bobs project")
    _create_table(
        client=client,
        caller="bob",
        project_id=bobs_project,
        datastore=warehouse,
        name="bobs_records",
    )

    listed = client.get(
        f"/projects/{bobs_project}/tables/", headers=headers_for(caller="bob")
    )

    assert listed.status_code == httpx.codes.OK, listed.text
    assert [table["name"] for table in listed.json()] == ["bobs_records"]


# --- when recording fails after the storage was made ------------------------
#
# Creating a table is two steps against two different systems: the storage is
# shaped, and then the platform records that the project holds it. The second
# one failing is what leaves a mess - storage nobody has a name for, in a
# project that can neither use it nor create it again. This cannot be arranged
# through the API, because there is no request that makes the database refuse
# a write, so it goes at the service directly.


async def test_the_storage_is_taken_back_out_when_it_cannot_be_recorded(
    client: TestClient, session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A table the platform failed to record is removed rather than abandoned."""
    warehouse_path = tmp_path / "warehouse.db"
    _register_datastore(client=client, session=session, path=warehouse_path)
    project_id = UUID(
        _create_project(client=client, caller="alice", name="alices project")
    )

    def refuse_to_commit() -> None:
        """Fail the write that records the table.

        Raises:
            RuntimeError: Always, standing in for a database that went away
                between shaping the storage and recording it.
        """
        raise RuntimeError("the database went away")

    monkeypatch.setattr(session, "commit", refuse_to_commit)

    with pytest.raises(RuntimeError, match="the database went away"):
        await tables_service.create_table(
            session=session,
            project_id=project_id,
            datastore_name="warehouse",
            name="orphan",
            description=None,
            columns=[ColumnDefinition(name="id", type="INTEGER", nullable=False)],
        )

    monkeypatch.undo()

    # Every file the datastore made: the table must not be in any of them.
    assert _tables_held_by(datastore_path=warehouse_path) == set()


async def test_the_project_can_create_the_table_again_afterwards(
    client: TestClient, session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is the whole point of clearing up: the name is free again.

    A project left holding storage it has no record of would be unable to
    create the table and unable to delete it, with nothing to do about it
    from outside the database.
    """
    _register_datastore(client=client, session=session, path=tmp_path / "warehouse.db")
    project = _create_project(client=client, caller="alice", name="alices project")

    def refuse_to_commit() -> None:
        """Fail the write that records the table.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("the database went away")

    monkeypatch.setattr(session, "commit", refuse_to_commit)
    with pytest.raises(RuntimeError):
        await tables_service.create_table(
            session=session,
            project_id=UUID(project),
            datastore_name="warehouse",
            name="records",
            description=None,
            columns=[ColumnDefinition(name="id", type="INTEGER", nullable=False)],
        )
    monkeypatch.undo()

    retried = _create_table(
        client=client, caller="alice", project_id=project, datastore="warehouse"
    )

    assert retried.status_code == httpx.codes.CREATED, retried.text
