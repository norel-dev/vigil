"""Tests of the list of storage a project chooses from.

Creating a blob or a table means naming a datastore, and datastores are the
platform's own: an ordinary user is refused every endpoint that touches one.
The catalogue is what keeps that from meaning "the choice exists but nobody
can make it", so these tests come in two halves.

The first is that the choice is now makeable: a project owner can see what is
on offer, narrow it to the stores that hold blobs, and use a name straight
from that list to create one.

The second is that nothing else came with it. The catalogue answers with a
name, a data type and a description, and a caller who reads it is no closer
to the storage than before - no endpoint, no credential, and no way through
any of the endpoints the catalogue sits beside.
"""

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.conftest import MinIOServer, headers_for, make_platform_admin


def _register_blob_store(
    *, client: TestClient, minio_server: MinIOServer, name: str, description: str
) -> None:
    """Register a MinIO datastore as the platform administrator.

    Args:
        client: The test client.
        minio_server: The running MinIO to point it at.
        name: Name to register the datastore under.
        description: What to say the datastore is for.
    """
    response = client.post(
        "/datastores/",
        json={
            "name": name,
            "description": description,
            "datastore": {
                "implementation": "minio",
                "endpoint": minio_server.endpoint,
                "access_key": minio_server.access_key,
                "secret_key": minio_server.secret_key,
                "secure": False,
            },
        },
        headers=headers_for(caller="root"),
    )
    assert response.status_code == httpx.codes.CREATED, response.text


def _register_table_store(*, client: TestClient, name: str, path: str) -> None:
    """Register a SQLite datastore as the platform administrator.

    Args:
        client: The test client.
        name: Name to register the datastore under.
        path: Where the SQLite file should live.
    """
    response = client.post(
        "/datastores/",
        json={
            "name": name,
            "description": "structured storage",
            "datastore": {
                "implementation": "sqlite",
                "sqlite_connection_string": path,
            },
        },
        headers=headers_for(caller="root"),
    )
    assert response.status_code == httpx.codes.CREATED, response.text


@pytest.fixture
def stocked_platform(
    client: TestClient, session: Session, minio_server: MinIOServer, tmp_path
) -> None:
    """Register one blob datastore and one table datastore.

    Args:
        client: The test client.
        session: A session on the test database, used to promote the caller.
        minio_server: The running MinIO to point the blob store at.
        tmp_path: Directory unique to the running test.
    """
    make_platform_admin(session=session, email="root@example.com")
    _register_blob_store(
        client=client,
        minio_server=minio_server,
        name="objects",
        description="object storage for the tests",
    )
    _register_table_store(
        client=client, name="warehouse", path=str(tmp_path / "warehouse.db")
    )


# --- the choice is makeable -------------------------------------------------


def test_a_regular_user_can_see_what_storage_exists(
    client: TestClient, stocked_platform: None
) -> None:
    """The whole point: a project owner has something to choose from.

    Alice holds no role on the platform at all beyond being a user, and
    `GET /datastores/` answers her with an empty list. This is what she reads
    instead.
    """
    response = client.get("/datastores/catalogue", headers=headers_for(caller="alice"))
    assert response.status_code == httpx.codes.OK, response.text

    assert {entry["name"] for entry in response.json()} == {"objects", "warehouse"}


def test_the_catalogue_says_what_each_store_holds(
    client: TestClient, stocked_platform: None
) -> None:
    """A name alone would not be enough to choose with."""
    response = client.get("/datastores/catalogue", headers=headers_for(caller="alice"))

    held = {entry["name"]: entry["data_type"] for entry in response.json()}
    assert held == {"objects": "blob", "warehouse": "table"}


def test_it_can_be_narrowed_to_the_stores_that_hold_blobs(
    client: TestClient, stocked_platform: None
) -> None:
    """Somebody about to create a blob asks for the stores a blob may go in."""
    response = client.get(
        "/datastores/catalogue",
        params={"data_type": "blob"},
        headers=headers_for(caller="alice"),
    )
    assert response.status_code == httpx.codes.OK, response.text

    assert [entry["name"] for entry in response.json()] == ["objects"]


def test_it_can_be_narrowed_to_the_stores_that_hold_tables(
    client: TestClient, stocked_platform: None
) -> None:
    """The same question, asked by somebody about to create a table."""
    response = client.get(
        "/datastores/catalogue",
        params={"data_type": "table"},
        headers=headers_for(caller="alice"),
    )

    assert [entry["name"] for entry in response.json()] == ["warehouse"]


def test_a_name_read_from_the_catalogue_is_one_a_blob_can_be_created_with(
    client: TestClient, stocked_platform: None
) -> None:
    """The end to end claim, with nothing about the datastore known in advance.

    Nothing in this test hardcodes a datastore name. Alice asks what holds
    blobs, takes the answer, and creates a blob in it - which is the whole
    journey the catalogue exists to make possible.
    """
    project = client.post(
        "/projects/",
        json={"name": "research", "description": None},
        headers=headers_for(caller="alice"),
    ).json()["id"]

    catalogue = client.get(
        "/datastores/catalogue",
        params={"data_type": "blob"},
        headers=headers_for(caller="alice"),
    ).json()
    chosen = catalogue[0]["name"]

    created = client.post(
        f"/projects/{project}/blobs/",
        json={
            "key": "notes.txt",
            "datastore": chosen,
            "content_type": "text/plain",
            "description": None,
        },
        headers=headers_for(caller="alice"),
    )
    assert created.status_code == httpx.codes.CREATED, created.text
    assert created.json()["blob"]["datastore_name"] == chosen

    stored = httpx.put(created.json()["upload"]["url"], content=b"chosen from a list")
    assert stored.status_code == httpx.codes.OK, stored.text


# --- and nothing else came with it ------------------------------------------


def test_the_catalogue_carries_no_way_to_reach_the_storage(
    client: TestClient, stocked_platform: None, minio_server: MinIOServer
) -> None:
    """An entry is a name, a data type and a description, and that is all."""
    response = client.get("/datastores/catalogue", headers=headers_for(caller="alice"))

    for entry in response.json():
        assert set(entry) == {"name", "data_type", "description"}

    assert minio_server.secret_key not in response.text
    assert minio_server.access_key not in response.text
    assert minio_server.endpoint not in response.text


def test_reading_the_catalogue_opens_no_other_door(
    client: TestClient, stocked_platform: None
) -> None:
    """Knowing a name is still not being allowed to use it.

    This is what stops the catalogue being a way around the system level: the
    endpoints that touch the connection behind a datastore refuse Alice
    exactly as they did before she could name one.
    """
    assert (
        client.get("/datastores/objects", headers=headers_for(caller="alice")).status_code
        == httpx.codes.FORBIDDEN
    )
    assert (
        client.get(
            "/datastores/query",
            params={"datastore": "objects", "query": ""},
            headers=headers_for(caller="alice"),
        ).status_code
        == httpx.codes.FORBIDDEN
    )
    assert (
        client.delete(
            "/datastores/objects", headers=headers_for(caller="alice")
        ).status_code
        == httpx.codes.FORBIDDEN
    )
    assert client.get("/datastores/", headers=headers_for(caller="alice")).json() == []


def test_the_catalogue_is_not_public(client: TestClient, stocked_platform: None) -> None:
    """The platform hands its list of storage to its own callers, not to anyone."""
    assert client.get("/datastores/catalogue").status_code == httpx.codes.UNAUTHORIZED


def test_an_empty_platform_has_an_empty_catalogue(client: TestClient) -> None:
    """Nothing registered is an answer, not an error."""
    response = client.get("/datastores/catalogue", headers=headers_for(caller="alice"))

    assert response.status_code == httpx.codes.OK, response.text
    assert response.json() == []
