"""Tests of `MinIODataStore` on its own, against a real MinIO.

The tests in `test_blob_access` go through the application and prove what a
role earns. These go straight at the implementation and prove what it does
with the store: that a namespace can be created twice, that an absent blob is
an ordinary answer rather than an error, and that a signature covers exactly
what it claims to.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
import urllib3
from minio import Minio
from pydantic import SecretStr

from src.features.blobs.storage import BlobOperation, BlobStorage
from src.features.datastores.implementations import MinIODataStore
from src.features.datastores.storage import DataStoreQuery, DataType, namespace_of
from src.platform.exceptions import BlobProvisioningError, QueryFailedError
from tests.conftest import MinIOServer

#: A host and port nothing is listening on, for the tests that need a store
#: that cannot be reached.
UNREACHABLE_ENDPOINT = "127.0.0.1:1"


@pytest.fixture
def store(minio_server: MinIOServer) -> MinIODataStore:
    """Return a datastore pointed at the running MinIO.

    Args:
        minio_server: The running MinIO to point it at.

    Returns:
        MinIODataStore: A store the tests can act through.
    """
    return MinIODataStore(
        endpoint=minio_server.endpoint,
        access_key=minio_server.access_key,
        secret_key=SecretStr(minio_server.secret_key),
        secure=False,
    )


@pytest.fixture
def namespace() -> str:
    """Return a namespace unique to the running test.

    Returns:
        str: A namespace name, derived as the platform derives them.
    """
    return namespace_of(project_id=uuid4())


async def test_it_reports_that_it_holds_blobs(store: MinIODataStore) -> None:
    """The platform picks a store by what it holds before using it."""
    assert await store.get_data_type() is DataType.BLOB


def test_it_satisfies_the_blob_storage_protocol(store: MinIODataStore) -> None:
    """Satisfying the protocol is what the service layer checks for."""
    assert isinstance(store, BlobStorage)


async def test_a_namespace_can_be_created_more_than_once(
    store: MinIODataStore, namespace: str
) -> None:
    """Every blob creation calls this, so it has to be safe to repeat."""
    await store.ensure_namespace(namespace=namespace)
    await store.ensure_namespace(namespace=namespace)

    assert await store.describe_blob(namespace=namespace, key="nothing.txt") is None


async def test_a_namespace_that_could_not_be_a_bucket_is_refused(
    store: MinIODataStore,
) -> None:
    """A name the platform did not derive never reaches the store."""
    with pytest.raises(BlobProvisioningError):
        await store.ensure_namespace(namespace="Not A Bucket Name")


async def test_describing_a_blob_that_was_never_uploaded_answers_none(
    store: MinIODataStore, namespace: str
) -> None:
    """An empty key is a normal state, so it is reported rather than raised."""
    await store.ensure_namespace(namespace=namespace)

    assert await store.describe_blob(namespace=namespace, key="missing.txt") is None


async def test_deleting_a_blob_that_is_not_there_is_not_an_error(
    store: MinIODataStore, namespace: str
) -> None:
    """A record whose bytes are gone still has to be removable."""
    await store.ensure_namespace(namespace=namespace)

    await store.delete_blob(namespace=namespace, key="missing.txt")


async def test_a_signed_url_round_trips_the_bytes(
    store: MinIODataStore, namespace: str
) -> None:
    """Upload and download both work without the platform carrying the data."""
    await store.ensure_namespace(namespace=namespace)

    upload = await store.presign(
        namespace=namespace,
        key="round/trip.txt",
        operation=BlobOperation.UPLOAD,
        expires_in=timedelta(minutes=5),
    )
    assert upload.method == "PUT"
    assert httpx.put(upload.url, content=b"there and back").status_code == httpx.codes.OK

    download = await store.presign(
        namespace=namespace,
        key="round/trip.txt",
        operation=BlobOperation.DOWNLOAD,
        expires_in=timedelta(minutes=5),
    )
    assert download.method == "GET"
    assert httpx.get(download.url).content == b"there and back"


async def test_describing_a_blob_reports_what_the_store_holds(
    store: MinIODataStore, namespace: str
) -> None:
    """Size and checksum are the store's facts, asked for rather than kept."""
    await store.ensure_namespace(namespace=namespace)
    upload = await store.presign(
        namespace=namespace,
        key="described.txt",
        operation=BlobOperation.UPLOAD,
        expires_in=timedelta(minutes=5),
    )
    httpx.put(upload.url, content=b"nine bytes")

    described = await store.describe_blob(namespace=namespace, key="described.txt")
    assert described is not None
    assert described.key == "described.txt"
    assert described.size == len(b"nine bytes")
    assert described.etag is not None


async def test_the_datastore_never_signs_for_longer_than_it_was_configured_to(
    minio_server: MinIOServer, namespace: str
) -> None:
    """Whoever set the datastore up has the final say on how long a URL lasts."""
    store = MinIODataStore(
        endpoint=minio_server.endpoint,
        access_key=minio_server.access_key,
        secret_key=SecretStr(minio_server.secret_key),
        secure=False,
        presigned_url_expiry_seconds=60,
    )
    await store.ensure_namespace(namespace=namespace)

    granted = await store.presign(
        namespace=namespace,
        key="brief.txt",
        operation=BlobOperation.DOWNLOAD,
        expires_in=timedelta(hours=12),
    )

    assert granted.expires_at <= datetime.now(tz=UTC) + timedelta(seconds=61)


async def test_querying_the_store_lists_what_is_in_it(
    store: MinIODataStore, namespace: str
) -> None:
    """Listing is what querying means where there is no query language."""
    await store.ensure_namespace(namespace=namespace)
    upload = await store.presign(
        namespace=namespace,
        key="listed/one.txt",
        operation=BlobOperation.UPLOAD,
        expires_in=timedelta(minutes=5),
    )
    httpx.put(upload.url, content=b"listed")

    buckets = await store.query(DataStoreQuery(query=""))
    assert namespace in {found["bucket"] for found in buckets.data}

    blobs = await store.query(DataStoreQuery(query=f"{namespace}/listed/"))
    assert [found["key"] for found in blobs.data] == ["listed/one.txt"]


def test_the_secret_key_does_not_escape_through_a_log_line(
    store: MinIODataStore, minio_server: MinIOServer
) -> None:
    """The credential has to survive being printed, not just being serialized.

    A redacting serializer only guards what goes through Pydantic. This is the
    other way out: a datastore interpolated into a log line or an exception
    message, which is how a secret usually ends up somewhere it should not be.
    """
    assert minio_server.secret_key not in repr(store)
    assert minio_server.secret_key not in str(store)
    assert minio_server.secret_key not in f"could not connect using {store}"

    # And it is still reachable where the platform actually needs it.
    assert store.secret_key.get_secret_value() == minio_server.secret_key


async def test_a_key_that_is_not_a_key_never_reaches_the_store(
    store: MinIODataStore, namespace: str
) -> None:
    """The implementation checks too, rather than trusting its caller."""
    with pytest.raises(ValueError):
        await store.presign(
            namespace=namespace,
            key="../escape.txt",
            operation=BlobOperation.DOWNLOAD,
            expires_in=timedelta(minutes=5),
        )


# --- when the store is not there --------------------------------------------
#
# Every call into MinIO can fail by the server simply not answering, and each
# one has to come back as the platform's own error rather than as a urllib3
# exception escaping through the router. The store below is pointed at a port
# nothing listens on, and is handed a client that gives up immediately: the
# default retries with backoff, which would make these the slowest tests in
# the suite for no extra confidence.


@pytest.fixture
def unreachable_store() -> MinIODataStore:
    """Return a store whose server is not there, and which finds out quickly.

    The client is seeded into the `_client` cached property rather than
    reached through it, which is the supported way to fill a cache before
    first use. What it changes is only how long the failure takes to arrive.

    Returns:
        MinIODataStore: A store pointed at a closed port.
    """
    store = MinIODataStore(
        endpoint=UNREACHABLE_ENDPOINT,
        access_key="unused",
        secret_key=SecretStr("unused"),
        secure=False,
    )
    store.__dict__["_client"] = Minio(
        endpoint=UNREACHABLE_ENDPOINT,
        access_key="unused",
        secret_key="unused",
        secure=False,
        http_client=urllib3.PoolManager(
            retries=urllib3.Retry(total=0, connect=0, read=0),
            timeout=urllib3.Timeout(connect=0.25, read=0.25),
        ),
    )
    return store


async def test_creating_a_namespace_in_a_store_that_is_not_there_is_reported(
    unreachable_store: MinIODataStore, namespace: str
) -> None:
    """The platform's own error, naming the store, rather than a socket error."""
    with pytest.raises(BlobProvisioningError, match="could not be reached"):
        await unreachable_store.ensure_namespace(namespace=namespace)


async def test_describing_a_blob_in_a_store_that_is_not_there_is_reported(
    unreachable_store: MinIODataStore, namespace: str
) -> None:
    """Absent and unreachable are different answers, and must not be confused.

    Describing a blob that is not there answers `None`, so a store that cannot
    be reached must raise instead - otherwise an outage would read as every
    blob having been emptied.
    """
    with pytest.raises(BlobProvisioningError, match="could not be reached"):
        await unreachable_store.describe_blob(namespace=namespace, key="report.txt")


async def test_deleting_a_blob_in_a_store_that_is_not_there_is_reported(
    unreachable_store: MinIODataStore, namespace: str
) -> None:
    """Deleting an absent blob is allowed to succeed; this has not deleted anything."""
    with pytest.raises(BlobProvisioningError, match="could not be reached"):
        await unreachable_store.delete_blob(namespace=namespace, key="report.txt")


async def test_listing_a_store_that_is_not_there_fails_rather_than_empties(
    unreachable_store: MinIODataStore,
) -> None:
    """An unreachable store holding nothing would be the wrong thing to report."""
    with pytest.raises(QueryFailedError, match="could not be reached"):
        await unreachable_store.query(DataStoreQuery(query=""))


async def test_signing_against_a_store_that_is_not_there_is_reported(
    unreachable_store: MinIODataStore, namespace: str
) -> None:
    """Signing is local arithmetic, but the region may be looked up first."""
    with pytest.raises(BlobProvisioningError, match="could not be reached"):
        await unreachable_store.presign(
            namespace=namespace,
            key="report.txt",
            operation=BlobOperation.DOWNLOAD,
            expires_in=timedelta(minutes=5),
        )


async def test_the_failure_never_carries_the_credential(namespace: str) -> None:
    """An unreachable store is interpolated into a log line and a 502 alike.

    `test_the_secret_key_does_not_escape_through_a_log_line` covers the store
    itself. This is the same question asked of the error, which is the thing
    that actually gets written down when a store goes away.
    """
    secret = "the-secret-nobody-should-see"
    store = MinIODataStore(
        endpoint=UNREACHABLE_ENDPOINT,
        access_key="an-access-key",
        secret_key=SecretStr(secret),
        secure=False,
    )
    store.__dict__["_client"] = Minio(
        endpoint=UNREACHABLE_ENDPOINT,
        access_key="an-access-key",
        secret_key=secret,
        secure=False,
        http_client=urllib3.PoolManager(
            retries=urllib3.Retry(total=0, connect=0, read=0),
            timeout=urllib3.Timeout(connect=0.25, read=0.25),
        ),
    )

    with pytest.raises(BlobProvisioningError) as failure:
        await store.ensure_namespace(namespace=namespace)

    assert secret not in str(failure.value)
