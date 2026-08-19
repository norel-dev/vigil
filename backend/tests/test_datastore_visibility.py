"""Tests of the datastores a platform administrator keeps to themselves.

The catalogue exists so that a user can find out what storage the platform
offers. Visibility is what lets an administrator register storage without
offering it: a public datastore is on that list, a private one is not.

These tests come in three halves, because the feature has three halves and
the third is the one that is easy to overstate.

The first is that private means absent. Not named and refused, not listed
with its details withheld - absent, because a name is the whole of what the
catalogue gives away.

The second is that hiding a datastore hides it from the list and from nothing
else. It is still the platform's own, its administrators still see it, still
read it, still query it, and can still publish it later.

The third is the honest one: a private datastore is not a protected
datastore. A user who is told the name can put a blob in it exactly as they
could a public one. That is asserted here rather than left implied, so that
nobody reads `visibility` as an access control and builds on it as though it
were.
"""

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.conftest import MinIOServer, headers_for, make_platform_admin


def _register_blob_store(
    *,
    client: TestClient,
    minio_server: MinIOServer,
    name: str,
    visibility: str | None = None,
) -> httpx.Response:
    """Register a MinIO datastore as the platform administrator.

    Args:
        client: The test client.
        minio_server: The running MinIO to point it at.
        name: Name to register the datastore under.
        visibility: The visibility to ask for, or None to say nothing and
            take whatever the platform defaults to.

    Returns:
        httpx.Response: What the platform answered.
    """
    body: dict = {
        "name": name,
        "description": f"storage called {name}",
        "datastore": {
            "implementation": "minio",
            "endpoint": minio_server.endpoint,
            "access_key": minio_server.access_key,
            "secret_key": minio_server.secret_key,
            "secure": False,
        },
    }
    if visibility is not None:
        body["visibility"] = visibility

    return client.post("/datastores/", json=body, headers=headers_for(caller="root"))


def _catalogue_names(*, client: TestClient, caller: str) -> set[str]:
    """Return the names of the datastores `caller` finds in the catalogue.

    Args:
        client: The test client.
        caller: Who is asking.

    Returns:
        set[str]: The names on offer to them.
    """
    response = client.get("/datastores/catalogue", headers=headers_for(caller=caller))
    assert response.status_code == httpx.codes.OK, response.text
    return {entry["name"] for entry in response.json()}


@pytest.fixture
def one_of_each(
    client: TestClient, session: Session, minio_server: MinIOServer
) -> None:
    """Register one public datastore and one private one.

    Args:
        client: The test client.
        session: A session on the test database, used to promote the caller.
        minio_server: The running MinIO to point both stores at.
    """
    make_platform_admin(session=session, email="root@example.com")

    offered = _register_blob_store(
        client=client, minio_server=minio_server, name="shared", visibility="public"
    )
    assert offered.status_code == httpx.codes.CREATED, offered.text

    kept = _register_blob_store(
        client=client, minio_server=minio_server, name="scratch", visibility="private"
    )
    assert kept.status_code == httpx.codes.CREATED, kept.text


# --- private means absent ---------------------------------------------------


def test_a_private_datastore_is_not_in_the_catalogue(
    client: TestClient, one_of_each: None
) -> None:
    """The whole point: Alice is offered the shared store and not the other."""
    assert _catalogue_names(client=client, caller="alice") == {"shared"}


def test_a_private_datastore_is_absent_rather_than_withheld(
    client: TestClient, one_of_each: None
) -> None:
    """Its name does not appear anywhere in the answer, in any form.

    A listing that named the store and withheld its details would have given
    away the only thing worth withholding, so this asserts on the raw body
    rather than on the parsed entries.
    """
    response = client.get("/datastores/catalogue", headers=headers_for(caller="alice"))

    assert "scratch" not in response.text


def test_narrowing_by_data_type_does_not_bring_it_back(
    client: TestClient, one_of_each: None
) -> None:
    """Both stores hold blobs, so this is the filter most likely to leak one."""
    response = client.get(
        "/datastores/catalogue",
        params={"data_type": "blob"},
        headers=headers_for(caller="alice"),
    )

    assert [entry["name"] for entry in response.json()] == ["shared"]


def test_it_is_hidden_from_the_administrator_who_registered_it_too(
    client: TestClient, one_of_each: None
) -> None:
    """The catalogue answers the same way for everybody, as it always did.

    Being a platform administrator is not what decides this listing, and it
    would be a strange thing for it to start deciding: the catalogue says
    what the platform *offers*, and a private store is not offered to anyone.
    Root reads the real list through `GET /datastores/` instead.
    """
    assert _catalogue_names(client=client, caller="root") == {"shared"}


def test_a_datastore_is_public_unless_the_administrator_says_otherwise(
    client: TestClient, session: Session, minio_server: MinIOServer
) -> None:
    """Registering storage is normally an offer to build on it.

    This is also what every datastore registered before visibility existed
    became, which is why the default is this way round.
    """
    make_platform_admin(session=session, email="root@example.com")
    created = _register_blob_store(
        client=client, minio_server=minio_server, name="objects"
    )

    assert created.status_code == httpx.codes.CREATED, created.text
    assert created.json()["visibility"] == "public"
    assert _catalogue_names(client=client, caller="alice") == {"objects"}


# --- hidden from the list, and from nothing else ----------------------------


def test_the_administrator_still_sees_it_in_the_real_listing(
    client: TestClient, one_of_each: None
) -> None:
    """A datastore nobody could find would be a datastore nobody could manage."""
    response = client.get("/datastores/", headers=headers_for(caller="root"))
    assert response.status_code == httpx.codes.OK, response.text

    listed = {store["name"]: store["visibility"] for store in response.json()}
    assert listed == {"shared": "public", "scratch": "private"}


def test_the_administrator_can_still_read_it_by_name(
    client: TestClient, one_of_each: None
) -> None:
    """Private changes what is offered, not what is the platform's own."""
    response = client.get("/datastores/scratch", headers=headers_for(caller="root"))

    assert response.status_code == httpx.codes.OK, response.text
    assert response.json()["visibility"] == "private"


def test_a_regular_user_is_refused_a_private_datastore_as_before(
    client: TestClient, one_of_each: None
) -> None:
    """Visibility took nothing away from the rules that were already there.

    Alice gets the same `403` on a private store that she gets on a public
    one: the endpoints that touch the connection behind a datastore are the
    platform's own either way, and the refusal does not depend on whether the
    name exists.
    """
    for name in ("shared", "scratch", "never-registered"):
        refused = client.get(f"/datastores/{name}", headers=headers_for(caller="alice"))
        assert refused.status_code == httpx.codes.FORBIDDEN, refused.text

    assert client.get("/datastores/", headers=headers_for(caller="alice")).json() == []


# --- publishing and withdrawing ---------------------------------------------


def test_a_private_datastore_can_be_published_later(
    client: TestClient, one_of_each: None
) -> None:
    """An administrator who set one up for themselves can offer it around."""
    published = client.patch(
        "/datastores/scratch",
        json={"visibility": "public"},
        headers=headers_for(caller="root"),
    )
    assert published.status_code == httpx.codes.OK, published.text
    assert published.json()["visibility"] == "public"

    assert _catalogue_names(client=client, caller="alice") == {"shared", "scratch"}


def test_a_public_datastore_can_be_withdrawn(
    client: TestClient, one_of_each: None
) -> None:
    """And the other way, for storage that should stop being offered."""
    withdrawn = client.patch(
        "/datastores/shared",
        json={"visibility": "private"},
        headers=headers_for(caller="root"),
    )
    assert withdrawn.status_code == httpx.codes.OK, withdrawn.text

    assert _catalogue_names(client=client, caller="alice") == set()


def test_only_a_platform_administrator_may_change_visibility(
    client: TestClient, one_of_each: None
) -> None:
    """Publishing storage is registering it again, as far as who may do it goes."""
    refused = client.patch(
        "/datastores/scratch",
        json={"visibility": "public"},
        headers=headers_for(caller="alice"),
    )
    assert refused.status_code == httpx.codes.FORBIDDEN, refused.text

    assert _catalogue_names(client=client, caller="alice") == {"shared"}


def test_publishing_a_datastore_that_does_not_exist_is_a_404(
    client: TestClient, one_of_each: None
) -> None:
    """For the administrator, who is allowed to know the difference."""
    response = client.patch(
        "/datastores/nowhere",
        json={"visibility": "public"},
        headers=headers_for(caller="root"),
    )

    assert response.status_code == httpx.codes.NOT_FOUND, response.text


# --- hidden is not protected ------------------------------------------------


def test_a_user_told_the_name_can_still_use_a_private_datastore(
    client: TestClient, one_of_each: None
) -> None:
    """The honest limit of the feature, asserted so that nobody assumes past it.

    Alice could not have found `scratch` on her own. Told it, she can put a
    blob in it and upload the bytes, exactly as she could with `shared`. This
    test is expected to keep passing: if visibility ever becomes an access
    control, it will be because somebody decided that on purpose and changed
    this test to say so.
    """
    project = client.post(
        "/projects/",
        json={"name": "research", "description": None},
        headers=headers_for(caller="alice"),
    ).json()["id"]

    created = client.post(
        f"/projects/{project}/blobs/",
        json={
            "key": "notes.txt",
            "datastore": "scratch",
            "content_type": "text/plain",
            "description": None,
        },
        headers=headers_for(caller="alice"),
    )
    assert created.status_code == httpx.codes.CREATED, created.text
    assert created.json()["blob"]["datastore_name"] == "scratch"

    stored = httpx.put(created.json()["upload"]["url"], content=b"told the name")
    assert stored.status_code == httpx.codes.OK, stored.text


def test_withdrawing_a_datastore_does_not_disturb_what_is_already_in_it(
    client: TestClient, one_of_each: None
) -> None:
    """A blob created while the store was public survives the store being hidden."""
    project = client.post(
        "/projects/",
        json={"name": "research", "description": None},
        headers=headers_for(caller="alice"),
    ).json()["id"]

    created = client.post(
        f"/projects/{project}/blobs/",
        json={
            "key": "notes.txt",
            "datastore": "shared",
            "content_type": "text/plain",
            "description": None,
        },
        headers=headers_for(caller="alice"),
    ).json()
    httpx.put(created["upload"]["url"], content=b"written while public")

    client.patch(
        "/datastores/shared",
        json={"visibility": "private"},
        headers=headers_for(caller="root"),
    )

    download = client.post(
        f"/projects/{project}/blobs/notes.txt/access",
        json={"operation": "download"},
        headers=headers_for(caller="alice"),
    )
    assert download.status_code == httpx.codes.OK, download.text

    fetched = httpx.get(download.json()["url"])
    assert fetched.content == b"written while public"
