"""End to end tests of who may do what to a project's blobs.

These go through the real application, the real policy engine and a real
MinIO, so what they pin down is the whole path: the role a caller holds
becomes a policy decision, the decision becomes a URL signed for one method on
one key, and MinIO is what honours or refuses it.

That last step is the reason these tests upload and download for real rather
than checking that a URL came back. A signed URL is the entire permission once
it leaves the platform, so a test that never used one would be checking that
the platform believes it granted something.

The case worth reading first is
`test_two_projects_sharing_a_datastore_never_see_each_other`. Two projects
share one MinIO and each name a blob the same thing, which is the arrangement
the platform exists to make safe.

The other half of that arrangement is that a project picks which datastore
each of its blobs goes to, and the tests under "choosing which datastore a
blob goes to" run against two separate MinIO servers so that the choice can
be checked by going and looking rather than by reading the record back.
"""

from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlmodel import Session

from src.features.datastores.implementations import MinIODataStore
from src.features.datastores.storage import namespace_of
from tests.conftest import MinIOServer, headers_for, make_platform_admin


def _register_datastore(
    *,
    client: TestClient,
    session: Session,
    minio_server: MinIOServer,
    name: str = "objects",
    expiry_seconds: int = 900,
) -> str:
    """Register a MinIO datastore, which only a platform administrator may do.

    Args:
        client: The test client.
        session: A session on the test database, used to promote the caller.
        minio_server: The running MinIO to point it at.
        name: Name to register the datastore under.
        expiry_seconds: How long the datastore should sign URLs for.

    Returns:
        str: The name of the registered datastore.
    """
    make_platform_admin(session=session, email="root@example.com")

    response = client.post(
        "/datastores/",
        json={
            "name": name,
            "description": "object storage for the tests",
            "datastore": {
                "implementation": "minio",
                "endpoint": minio_server.endpoint,
                "access_key": minio_server.access_key,
                "secret_key": minio_server.secret_key,
                "secure": False,
                "presigned_url_expiry_seconds": expiry_seconds,
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


def _create_blob(
    *,
    client: TestClient,
    caller: str,
    project_id: str,
    datastore: str,
    key: str = "notes.txt",
) -> httpx.Response:
    """Ask for a blob to be recorded, and return the raw response.

    Args:
        client: The test client.
        caller: The name of the caller.
        project_id: The project the blob belongs to.
        datastore: Name of the datastore that should hold it.
        key: What the project calls the blob.

    Returns:
        httpx.Response: Whatever the API answered.
    """
    return client.post(
        f"/projects/{project_id}/blobs/",
        json={
            "key": key,
            "datastore": datastore,
            "content_type": "text/plain",
            "description": None,
        },
        headers=headers_for(caller=caller),
    )


def _access(
    *,
    client: TestClient,
    caller: str,
    project_id: str,
    key: str,
    operation: str,
) -> httpx.Response:
    """Ask for a URL to reach a blob's contents, and return the raw response.

    Args:
        client: The test client.
        caller: The name of the caller.
        project_id: The project the blob belongs to.
        key: What the project calls the blob.
        operation: Either "download" or "upload".

    Returns:
        httpx.Response: Whatever the API answered.
    """
    return client.post(
        f"/projects/{project_id}/blobs/{key}/access",
        json={"operation": operation},
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
def objects(client: TestClient, session: Session, minio_server: MinIOServer) -> str:
    """Return the name of a registered datastore that holds blobs.

    Args:
        client: The test client.
        session: A session on the test database.
        minio_server: The running MinIO to point it at.

    Returns:
        str: The datastore's name.
    """
    return _register_datastore(
        client=client, session=session, minio_server=minio_server
    )


@pytest.fixture
def other_objects(
    client: TestClient, session: Session, other_minio_server: MinIOServer
) -> str:
    """Return the name of a second blob datastore, on a different server.

    The two stores share nothing, so a blob is either in one or in the other
    and a test can say which by looking rather than by trusting the record.

    Args:
        client: The test client.
        session: A session on the test database.
        other_minio_server: A second running MinIO, unrelated to the first.

    Returns:
        str: The datastore's name.
    """
    return _register_datastore(
        client=client,
        session=session,
        minio_server=other_minio_server,
        name="archive",
    )


@pytest.fixture
def project(client: TestClient) -> str:
    """Return the id of a project Alice owns.

    Args:
        client: The test client.

    Returns:
        str: The project's id.
    """
    return _create_project(client=client, caller="alice", name="research")


# --- the ordinary path ------------------------------------------------------


def test_an_owner_creates_a_blob_and_uploads_through_the_url_they_are_handed(
    client: TestClient, objects: str, project: str
) -> None:
    """Creating a blob answers with a URL that really does accept the data."""
    created = _create_blob(
        client=client, caller="alice", project_id=project, datastore=objects
    )
    assert created.status_code == httpx.codes.CREATED, created.text

    upload = created.json()["upload"]
    assert upload["method"] == "PUT"

    stored = httpx.put(upload["url"], content=b"the contents")
    assert stored.status_code == httpx.codes.OK, stored.text


def test_a_blob_is_recorded_before_it_holds_anything(
    client: TestClient, objects: str, project: str
) -> None:
    """A blob with no bytes behind it is reported as such, not as missing."""
    _create_blob(client=client, caller="alice", project_id=project, datastore=objects)

    response = client.get(
        f"/projects/{project}/blobs/notes.txt", headers=headers_for(caller="alice")
    )
    assert response.status_code == httpx.codes.OK, response.text
    assert response.json()["blob"]["key"] == "notes.txt"
    assert response.json()["stored"] is None


def test_reading_a_blob_reports_what_the_store_holds_once_it_is_filled(
    client: TestClient, objects: str, project: str
) -> None:
    """Size and checksum come from the store rather than from the record."""
    created = _create_blob(
        client=client, caller="alice", project_id=project, datastore=objects
    )
    httpx.put(created.json()["upload"]["url"], content=b"twelve bytes")

    response = client.get(
        f"/projects/{project}/blobs/notes.txt", headers=headers_for(caller="alice")
    )
    assert response.status_code == httpx.codes.OK, response.text
    assert response.json()["stored"]["size"] == len(b"twelve bytes")
    assert response.json()["stored"]["etag"] is not None


def test_a_download_url_returns_the_bytes_that_were_uploaded(
    client: TestClient, objects: str, project: str
) -> None:
    """The whole round trip works without the API ever carrying the data."""
    created = _create_blob(
        client=client, caller="alice", project_id=project, datastore=objects
    )
    httpx.put(created.json()["upload"]["url"], content=b"the contents")

    granted = _access(
        client=client,
        caller="alice",
        project_id=project,
        key="notes.txt",
        operation="download",
    )
    assert granted.status_code == httpx.codes.OK, granted.text
    assert granted.json()["method"] == "GET"

    fetched = httpx.get(granted.json()["url"])
    assert fetched.status_code == httpx.codes.OK
    assert fetched.content == b"the contents"


def test_a_key_with_slashes_is_one_name_rather_than_a_folder(
    client: TestClient, objects: str, project: str
) -> None:
    """Nothing has to be created before a key that reads like a path is used."""
    created = _create_blob(
        client=client,
        caller="alice",
        project_id=project,
        datastore=objects,
        key="reports/2026/q1.csv",
    )
    assert created.status_code == httpx.codes.CREATED, created.text

    httpx.put(created.json()["upload"]["url"], content=b"a,b\n1,2\n")

    response = client.get(
        f"/projects/{project}/blobs/reports/2026/q1.csv",
        headers=headers_for(caller="alice"),
    )
    assert response.status_code == httpx.codes.OK, response.text
    assert response.json()["stored"]["size"] == len(b"a,b\n1,2\n")


def test_listing_can_be_narrowed_to_a_prefix(
    client: TestClient, objects: str, project: str
) -> None:
    """Prefixes are the only hierarchy blobs have, and listing honours them."""
    for key in ("reports/q1.csv", "reports/q2.csv", "models/latest.pkl"):
        _create_blob(
            client=client,
            caller="alice",
            project_id=project,
            datastore=objects,
            key=key,
        )

    everything = client.get(
        f"/projects/{project}/blobs/", headers=headers_for(caller="alice")
    )
    assert {blob["key"] for blob in everything.json()} == {
        "reports/q1.csv",
        "reports/q2.csv",
        "models/latest.pkl",
    }

    narrowed = client.get(
        f"/projects/{project}/blobs/",
        params={"prefix": "reports/"},
        headers=headers_for(caller="alice"),
    )
    assert {blob["key"] for blob in narrowed.json()} == {
        "reports/q1.csv",
        "reports/q2.csv",
    }


def test_deleting_a_blob_removes_the_data_and_the_record(
    client: TestClient, objects: str, project: str
) -> None:
    """Both halves go, so nothing is left that the platform cannot account for."""
    created = _create_blob(
        client=client, caller="alice", project_id=project, datastore=objects
    )
    download = _access(
        client=client,
        caller="alice",
        project_id=project,
        key="notes.txt",
        operation="download",
    ).json()["url"]
    httpx.put(created.json()["upload"]["url"], content=b"the contents")

    deleted = client.delete(
        f"/projects/{project}/blobs/notes.txt", headers=headers_for(caller="alice")
    )
    assert deleted.status_code == httpx.codes.NO_CONTENT, deleted.text

    gone = client.get(
        f"/projects/{project}/blobs/notes.txt", headers=headers_for(caller="alice")
    )
    assert gone.status_code == httpx.codes.NOT_FOUND

    # The URL signed before the delete is still validly signed, and now finds
    # nothing - which is the store enforcing the deletion, not the platform.
    assert httpx.get(download).status_code == httpx.codes.NOT_FOUND


def test_a_blob_whose_data_was_never_uploaded_can_still_be_deleted(
    client: TestClient, objects: str, project: str
) -> None:
    """A record must never outlive the platform's ability to remove it."""
    _create_blob(client=client, caller="alice", project_id=project, datastore=objects)

    deleted = client.delete(
        f"/projects/{project}/blobs/notes.txt", headers=headers_for(caller="alice")
    )
    assert deleted.status_code == httpx.codes.NO_CONTENT, deleted.text


# --- what each role may do --------------------------------------------------


def test_a_viewer_may_download_but_not_upload(
    client: TestClient, objects: str, project: str
) -> None:
    """The two are separate permissions, so the refusal comes before the URL."""
    _create_blob(client=client, caller="alice", project_id=project, datastore=objects)
    _grant(
        client=client,
        owner="alice",
        project_id=project,
        email="bob@example.com",
        role="viewer",
    )

    download = _access(
        client=client,
        caller="bob",
        project_id=project,
        key="notes.txt",
        operation="download",
    )
    assert download.status_code == httpx.codes.OK, download.text

    upload = _access(
        client=client,
        caller="bob",
        project_id=project,
        key="notes.txt",
        operation="upload",
    )
    assert upload.status_code == httpx.codes.FORBIDDEN


def test_an_editor_may_upload(client: TestClient, objects: str, project: str) -> None:
    """An editor changes a blob's contents, as they change a table's rows."""
    _create_blob(client=client, caller="alice", project_id=project, datastore=objects)
    _grant(
        client=client,
        owner="alice",
        project_id=project,
        email="bob@example.com",
        role="editor",
    )

    granted = _access(
        client=client,
        caller="bob",
        project_id=project,
        key="notes.txt",
        operation="upload",
    )
    assert granted.status_code == httpx.codes.OK, granted.text

    stored = httpx.put(granted.json()["url"], content=b"bob was here")
    assert stored.status_code == httpx.codes.OK, stored.text


def test_an_editor_may_not_create_or_delete_a_blob(
    client: TestClient, objects: str, project: str
) -> None:
    """Claiming and destroying a name in shared storage stays with the owner."""
    _create_blob(client=client, caller="alice", project_id=project, datastore=objects)
    _grant(
        client=client,
        owner="alice",
        project_id=project,
        email="bob@example.com",
        role="editor",
    )

    created = _create_blob(
        client=client,
        caller="bob",
        project_id=project,
        datastore=objects,
        key="bobs.txt",
    )
    assert created.status_code == httpx.codes.FORBIDDEN

    deleted = client.delete(
        f"/projects/{project}/blobs/notes.txt", headers=headers_for(caller="bob")
    )
    assert deleted.status_code == httpx.codes.FORBIDDEN


def test_a_stranger_reaches_nothing(
    client: TestClient, objects: str, project: str
) -> None:
    """Somebody with no role in the project is refused at every door."""
    _create_blob(client=client, caller="alice", project_id=project, datastore=objects)

    read = client.get(
        f"/projects/{project}/blobs/notes.txt", headers=headers_for(caller="bob")
    )
    assert read.status_code == httpx.codes.FORBIDDEN

    download = _access(
        client=client,
        caller="bob",
        project_id=project,
        key="notes.txt",
        operation="download",
    )
    assert download.status_code == httpx.codes.FORBIDDEN

    listed = client.get(
        f"/projects/{project}/blobs/", headers=headers_for(caller="bob")
    )
    assert listed.status_code == httpx.codes.OK
    assert listed.json() == []


# --- isolation --------------------------------------------------------------


def test_two_projects_sharing_a_datastore_never_see_each_other(
    client: TestClient, objects: str
) -> None:
    """The arrangement the platform exists to make safe.

    Both projects use one MinIO and both call their blob `notes.txt`. Neither
    key had to be rewritten, and neither project can reach the other's bytes.
    """
    alices = _create_project(client=client, caller="alice", name="alices")
    bobs = _create_project(client=client, caller="bob", name="bobs")

    for caller, project_id, contents in (
        ("alice", alices, b"alice's data"),
        ("bob", bobs, b"bob's data"),
    ):
        created = _create_blob(
            client=client, caller=caller, project_id=project_id, datastore=objects
        )
        assert created.status_code == httpx.codes.CREATED, created.text
        httpx.put(created.json()["upload"]["url"], content=contents)

    for caller, project_id, expected in (
        ("alice", alices, b"alice's data"),
        ("bob", bobs, b"bob's data"),
    ):
        granted = _access(
            client=client,
            caller=caller,
            project_id=project_id,
            key="notes.txt",
            operation="download",
        )
        assert httpx.get(granted.json()["url"]).content == expected

    # And neither may ask the platform for the other's blob at all.
    trespass = _access(
        client=client,
        caller="bob",
        project_id=alices,
        key="notes.txt",
        operation="download",
    )
    assert trespass.status_code == httpx.codes.FORBIDDEN


def test_a_project_may_not_take_a_key_twice(
    client: TestClient, objects: str, project: str
) -> None:
    """Within one project a key names one blob, so the second is refused."""
    _create_blob(client=client, caller="alice", project_id=project, datastore=objects)
    again = _create_blob(
        client=client, caller="alice", project_id=project, datastore=objects
    )
    assert again.status_code == httpx.codes.CONFLICT


# --- what a signed URL is not good for --------------------------------------


def test_a_download_url_cannot_be_used_to_upload(
    client: TestClient, objects: str, project: str
) -> None:
    """The signature covers the method, and MinIO is what refuses the rest.

    This is the blob equivalent of handing a caller a read-only connection:
    the platform is not in the path of the request, so the boundary has to
    hold without it.
    """
    _create_blob(client=client, caller="alice", project_id=project, datastore=objects)

    granted = _access(
        client=client,
        caller="alice",
        project_id=project,
        key="notes.txt",
        operation="download",
    )

    refused = httpx.put(granted.json()["url"], content=b"should not land")
    assert refused.status_code == httpx.codes.FORBIDDEN


def test_a_url_signed_for_one_blob_cannot_be_pointed_at_another(
    client: TestClient, objects: str, project: str
) -> None:
    """The key is signed over too, so editing it invalidates the signature."""
    for key in ("mine.txt", "secret.txt"):
        created = _create_blob(
            client=client,
            caller="alice",
            project_id=project,
            datastore=objects,
            key=key,
        )
        httpx.put(created.json()["upload"]["url"], content=f"{key} data".encode())

    granted = _access(
        client=client,
        caller="alice",
        project_id=project,
        key="mine.txt",
        operation="download",
    )

    tampered = granted.json()["url"].replace("mine.txt", "secret.txt")
    assert httpx.get(tampered).status_code == httpx.codes.FORBIDDEN


# --- refusing what is not a blob key ----------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "../escape.txt",
        "nested/../../escape.txt",
        "/leading.txt",
        "double//slash.txt",
        "spaces are out.txt",
    ],
)
def test_a_key_that_could_mean_more_than_one_place_is_refused(
    client: TestClient, objects: str, project: str, key: str
) -> None:
    """A key has to name one fixed blob, and these do not."""
    created = _create_blob(
        client=client, caller="alice", project_id=project, datastore=objects, key=key
    )
    assert created.status_code == httpx.codes.UNPROCESSABLE_ENTITY, created.text


# --- the datastore itself ---------------------------------------------------


def test_a_blob_cannot_be_put_in_a_datastore_that_holds_tables(
    client: TestClient, session: Session, project: str, tmp_path
) -> None:
    """The platform checks the store can hold what is being asked of it."""
    make_platform_admin(session=session, email="root@example.com")
    client.post(
        "/datastores/",
        json={
            "name": "warehouse",
            "description": "tables, not blobs",
            "datastore": {
                "implementation": "sqlite",
                "sqlite_connection_string": str(tmp_path / "warehouse.db"),
            },
        },
        headers=headers_for(caller="root"),
    )

    created = _create_blob(
        client=client, caller="alice", project_id=project, datastore="warehouse"
    )
    assert created.status_code == httpx.codes.BAD_REQUEST, created.text
    assert "does not hold blobs" in created.text


def test_the_minio_secret_key_never_leaves_the_api(
    client: TestClient, session: Session, objects: str, minio_server: MinIOServer
) -> None:
    """A platform administrator reading a datastore is not handed its credential.

    The secret is in the database, because the platform has to reconnect with
    it. It is not in the answer, because nobody reading a datastore needs it.
    """
    response = client.get(f"/datastores/{objects}", headers=headers_for(caller="root"))
    assert response.status_code == httpx.codes.OK, response.text

    implementation = response.json()["implementation"]
    assert implementation["access_key"] == minio_server.access_key
    assert implementation["secret_key"] != minio_server.secret_key
    assert minio_server.secret_key not in response.text


# --- choosing which datastore a blob goes to --------------------------------
#
# The platform holds more than one blob datastore at a time - fast and local
# beside slow and cheap, one region beside another - and a project says which
# one it means per blob, at the moment it creates it. These are the tests that
# the choice is really honoured, rather than recorded and then ignored: the
# two datastores here are two separate MinIO servers, so a blob in the wrong
# one is not a mislabelled row, it is bytes on the wrong machine.


def test_a_project_chooses_which_datastore_each_blob_goes_to(
    client: TestClient, objects: str, other_objects: str, project: str
) -> None:
    """One project, two datastores, one blob in each, both round tripping."""
    for datastore, key, contents in (
        (objects, "near.txt", b"kept close"),
        (other_objects, "far.txt", b"kept far away"),
    ):
        created = _create_blob(
            client=client,
            caller="alice",
            project_id=project,
            datastore=datastore,
            key=key,
        )
        assert created.status_code == httpx.codes.CREATED, created.text
        assert created.json()["blob"]["datastore_name"] == datastore

        assert httpx.put(
            created.json()["upload"]["url"], content=contents
        ).status_code == httpx.codes.OK

    # Downloading needs only the key: which store each blob went to was
    # settled above, and is what the platform now has to remember on its own.
    for key, contents in (("near.txt", b"kept close"), ("far.txt", b"kept far away")):
        granted = _access(
            client=client,
            caller="alice",
            project_id=project,
            key=key,
            operation="download",
        )
        assert granted.status_code == httpx.codes.OK, granted.text
        assert httpx.get(granted.json()["url"]).content == contents


async def test_a_blob_is_written_to_the_chosen_store_and_to_no_other(
    client: TestClient,
    project: str,
    objects: str,
    other_objects: str,
    minio_server: MinIOServer,
    other_minio_server: MinIOServer,
) -> None:
    """The bytes are where the caller asked for them, and nowhere else.

    Asking the two servers directly is the point of this test. That the record
    names a datastore proves only what the platform believes; going to both
    stores and finding the blob in one of them is what proves the choice was
    carried out.
    """
    created = _create_blob(
        client=client,
        caller="alice",
        project_id=project,
        datastore=other_objects,
        key="chosen.txt",
    )
    assert created.status_code == httpx.codes.CREATED, created.text
    httpx.put(created.json()["upload"]["url"], content=b"in the archive")

    namespace = namespace_of(project_id=UUID(project))

    chosen = MinIODataStore(
        endpoint=other_minio_server.endpoint,
        access_key=other_minio_server.access_key,
        secret_key=SecretStr(other_minio_server.secret_key),
        secure=False,
    )
    held = await chosen.describe_blob(namespace=namespace, key="chosen.txt")
    assert held is not None
    assert held.size == len(b"in the archive")

    not_chosen = MinIODataStore(
        endpoint=minio_server.endpoint,
        access_key=minio_server.access_key,
        secret_key=SecretStr(minio_server.secret_key),
        secure=False,
    )
    assert await not_chosen.describe_blob(namespace=namespace, key="chosen.txt") is None


def test_the_url_handed_back_points_at_the_chosen_store(
    client: TestClient,
    project: str,
    objects: str,
    other_objects: str,
    other_minio_server: MinIOServer,
) -> None:
    """A signed URL is signed by one store, and says which one it came from."""
    created = _create_blob(
        client=client,
        caller="alice",
        project_id=project,
        datastore=other_objects,
        key="chosen.txt",
    )

    assert other_minio_server.endpoint in created.json()["upload"]["url"]


def test_the_datastore_a_blob_lives_in_is_reported_back(
    client: TestClient, objects: str, other_objects: str, project: str
) -> None:
    """Reading and listing both say where a blob is, so a choice is reviewable."""
    _create_blob(
        client=client,
        caller="alice",
        project_id=project,
        datastore=other_objects,
        key="far.txt",
    )

    read = client.get(
        f"/projects/{project}/blobs/far.txt", headers=headers_for(caller="alice")
    )
    assert read.json()["blob"]["datastore_name"] == other_objects

    listed = client.get(
        f"/projects/{project}/blobs/", headers=headers_for(caller="alice")
    )
    assert [blob["datastore_name"] for blob in listed.json()] == [other_objects]


def test_choosing_a_datastore_that_does_not_exist_is_a_404(
    client: TestClient, objects: str, project: str
) -> None:
    """A name that names nothing is a mistake in the request, and says so."""
    created = _create_blob(
        client=client,
        caller="alice",
        project_id=project,
        datastore="no-such-store",
        key="nowhere.txt",
    )
    assert created.status_code == httpx.codes.NOT_FOUND, created.text


def test_a_blob_in_a_store_that_cannot_be_reached_is_a_502_not_a_500(
    client: TestClient, session: Session, project: str
) -> None:
    """Choosing a datastore that is not there is the caller's ordinary mistake.

    Nothing is wrong with the platform when this happens, so it does not
    answer as though there were: the store behind the chosen datastore did not
    answer, and 502 is what says that.
    """
    make_platform_admin(session=session, email="root@example.com")
    registered = client.post(
        "/datastores/",
        json={
            "name": "unplugged",
            "description": "points at nothing at all",
            "datastore": {
                "implementation": "minio",
                "endpoint": "127.0.0.1:1",
                "access_key": "nobody",
                "secret_key": "nothing",
                "secure": False,
            },
        },
        headers=headers_for(caller="root"),
    )
    assert registered.status_code == httpx.codes.CREATED, registered.text

    created = _create_blob(
        client=client, caller="alice", project_id=project, datastore="unplugged"
    )
    assert created.status_code == httpx.codes.BAD_GATEWAY, created.text
    assert "could not be reached" in created.text
