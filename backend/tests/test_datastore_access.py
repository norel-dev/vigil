"""End to end tests of who may reach the platform's datastores.

Datastores describe the storage the platform itself is built on, so the rule
these tests pin down is a simple one: platform administrators manage them, and
nobody else can see them at all. Every request goes through the real routers,
authenticating with a real API key, and a real Open Policy Agent evaluating the
real policy.
"""

import sqlite3
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.conftest import headers_for, make_platform_admin


def _create_datastore(
    *,
    client: TestClient,
    caller: str,
    name: str,
    database_path: Path,
) -> httpx.Response:
    """Ask the API to register a SQLite datastore.

    Args:
        client: The test client.
        caller: The name of the caller.
        name: Name of the new datastore.
        database_path: The SQLite file it points at.

    Returns:
        httpx.Response: Whatever the API answered.
    """
    return client.post(
        "/datastores/",
        json={
            "name": name,
            "description": None,
            "datastore": {
                "implementation": "sqlite",
                "sqlite_connection_string": str(database_path),
            },
        },
        headers=headers_for(caller=caller),
    )


def _make_queryable_database(*, path: Path) -> None:
    """Create a SQLite database holding one row, so queries return something.

    Args:
        path: Where the database file should be created.
    """
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE readings (value INTEGER)")
        connection.execute("INSERT INTO readings VALUES (42)")


def _make_administrator(*, session: Session) -> None:
    """Promote 'root' to platform administrator.

    Args:
        session: An open session on the test database.
    """
    make_platform_admin(session=session, email="root@example.com")


def test_a_platform_administrator_manages_a_datastore_end_to_end(
    client: TestClient, session: Session, tmp_path: Path
) -> None:
    """Registering, reading, querying and forgetting a datastore all work."""
    database_path = tmp_path / "warehouse.db"
    _make_queryable_database(path=database_path)
    _make_administrator(session=session)

    created = _create_datastore(
        client=client, caller="root", name="warehouse", database_path=database_path
    )
    assert created.status_code == httpx.codes.CREATED, created.text

    read = client.get("/datastores/warehouse", headers=headers_for(caller="root"))
    assert read.status_code == httpx.codes.OK, read.text

    queried = client.get(
        "/datastores/query",
        params={"datastore": "warehouse", "query": "SELECT value FROM readings"},
        headers=headers_for(caller="root"),
    )
    assert queried.status_code == httpx.codes.OK, queried.text
    assert queried.json()["data"] == [[42]]

    forgotten = client.delete("/datastores/warehouse", headers=headers_for(caller="root"))
    assert forgotten.status_code == httpx.codes.NO_CONTENT, forgotten.text


def test_a_regular_user_cannot_register_a_datastore(
    client: TestClient, tmp_path: Path
) -> None:
    """This is the case the change exists to enforce: storage is not user land."""

    response = _create_datastore(
        client=client, caller="alice", name="alices store", database_path=tmp_path / "a.db"
    )

    assert response.status_code == httpx.codes.FORBIDDEN, response.text
    assert "only platform administrators" in response.json()["reason"]


def test_a_regular_user_cannot_read_or_query_a_datastore(
    client: TestClient, session: Session, tmp_path: Path
) -> None:
    """Denial covers the connection details as well as the data behind them."""
    database_path = tmp_path / "warehouse.db"
    _make_queryable_database(path=database_path)
    _make_administrator(session=session)
    _create_datastore(
        client=client, caller="root", name="warehouse", database_path=database_path
    )

    read = client.get("/datastores/warehouse", headers=headers_for(caller="alice"))
    assert read.status_code == httpx.codes.FORBIDDEN, read.text

    queried = client.get(
        "/datastores/query",
        params={"datastore": "warehouse", "query": "SELECT value FROM readings"},
        headers=headers_for(caller="alice"),
    )
    assert queried.status_code == httpx.codes.FORBIDDEN, queried.text


def test_a_regular_user_cannot_delete_a_datastore(
    client: TestClient, session: Session, tmp_path: Path
) -> None:
    """Forgetting a datastore is as privileged as registering one."""
    _make_administrator(session=session)
    _create_datastore(
        client=client, caller="root", name="warehouse", database_path=tmp_path / "w.db"
    )

    response = client.delete("/datastores/warehouse", headers=headers_for(caller="alice"))

    assert response.status_code == httpx.codes.FORBIDDEN, response.text


def test_owning_a_project_grants_nothing_over_datastores(
    client: TestClient, session: Session, tmp_path: Path
) -> None:
    """Owning a project is the most a regular user can be, and it is not enough.

    This is what distinguishes the new model from the old one: rights inside a
    project stop at the project's edge, and datastores are outside it.
    """
    _make_administrator(session=session)
    _create_datastore(
        client=client, caller="root", name="warehouse", database_path=tmp_path / "w.db"
    )

    created_project = client.post(
        "/projects/",
        json={"name": "alices project", "description": None},
        headers=headers_for(caller="alice"),
    )
    assert created_project.status_code == httpx.codes.CREATED, created_project.text

    response = client.get("/datastores/warehouse", headers=headers_for(caller="alice"))

    assert response.status_code == httpx.codes.FORBIDDEN, response.text


def test_listing_datastores_shows_a_regular_user_nothing(
    client: TestClient, session: Session, tmp_path: Path
) -> None:
    """A listing is filtered by the same policy that guards a direct read."""
    _make_administrator(session=session)
    _create_datastore(
        client=client, caller="root", name="warehouse", database_path=tmp_path / "w.db"
    )
    _create_datastore(
        client=client, caller="root", name="lake", database_path=tmp_path / "l.db"
    )

    for_a_user = client.get("/datastores/", headers=headers_for(caller="alice"))
    assert for_a_user.status_code == httpx.codes.OK, for_a_user.text
    assert for_a_user.json() == []

    for_an_administrator = client.get("/datastores/", headers=headers_for(caller="root"))
    assert for_an_administrator.status_code == httpx.codes.OK, for_an_administrator.text
    assert {store["name"] for store in for_an_administrator.json()} == {"warehouse", "lake"}


def test_a_refusal_does_not_reveal_whether_the_datastore_exists(
    client: TestClient, session: Session, tmp_path: Path
) -> None:
    """A regular user gets the same answer for a real name and an invented one.

    The policy is consulted before the lookup, so the difference between a
    `403` and a `404` never becomes a way to enumerate the platform's storage.
    """
    _make_administrator(session=session)
    _create_datastore(
        client=client, caller="root", name="warehouse", database_path=tmp_path / "w.db"
    )

    real = client.get("/datastores/warehouse", headers=headers_for(caller="alice"))
    invented = client.get("/datastores/no such store", headers=headers_for(caller="alice"))

    assert real.status_code == httpx.codes.FORBIDDEN, real.text
    assert invented.status_code == httpx.codes.FORBIDDEN, invented.text

    # The administrator, who is allowed to look, is told the truth.
    for_an_administrator = client.get(
        "/datastores/no such store", headers=headers_for(caller="root")
    )
    assert for_an_administrator.status_code == httpx.codes.NOT_FOUND


def test_requests_without_a_credential_are_refused(client: TestClient) -> None:
    """The endpoints are not reachable anonymously."""
    response = client.get("/datastores/")

    assert response.status_code == httpx.codes.UNAUTHORIZED


def test_an_unknown_credential_is_refused(client: TestClient) -> None:
    """A token the identity provider does not recognise gets nowhere."""
    response = client.get("/datastores/", headers=headers_for(caller="mallory"))

    assert response.status_code == httpx.codes.UNAUTHORIZED
