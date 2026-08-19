"""Recording, describing and signing access to the blobs a project holds.

The endpoints in front of this module decide *whether* a caller may touch a
blob; this module knows *how* to reach it, and is the only place that knows a
blob has a life outside the platform's database. Everything here goes through
the `BlobStorage` protocol, so nothing in it mentions MinIO or S3.

The orderings here are the opposite way round from tables, and deliberately
so. A table has to be provisioned before it can be recorded, because an
unrecorded table is storage nobody can name or clean up. A blob has nothing
to provision: the key exists the moment somebody uploads to it. So creating
records the blob first and hands back a URL to fill it with, and the state in
between - a record with no bytes behind it - is an ordinary one that reading
reports honestly. Deleting still destroys the data first and forgets the
record second, for the same reason it does for tables: if the store cannot be
reached, the platform should go on describing something that really is there.
"""

from datetime import timedelta
from uuid import UUID

from sqlmodel import Session, col, select

from src.features.blobs.model import Blob
from src.features.blobs.storage import (
    BlobDescription,
    BlobOperation,
    BlobStorage,
    PresignedAccess,
    validate_object_key,
)
from src.features.datastores import service as datastores_service
from src.features.datastores.storage import DataType, namespace_of
from src.platform.exceptions import (
    DuplicateObjectError,
    ObjectNotFoundError,
    UnsuitableDataStoreError,
)

__all__ = [
    "create_blob",
    "delete_blob",
    "describe_blob",
    "get_blob",
    "grant_access",
    "list_blobs",
]


async def _storage_behind(*, session: Session, datastore_name: str) -> BlobStorage:
    """Return the blob storage of the datastore called `datastore_name`.

    Args:
        session: The open database session.
        datastore_name: Name of the datastore to reach.

    Returns:
        BlobStorage: The datastore's implementation, as blob storage.

    Raises:
        ObjectNotFoundError: If no datastore has that name.
        UnsuitableDataStoreError: If that datastore does not hold blobs.
    """
    store = datastores_service.get_datastore(session=session, name=datastore_name)
    implementation = store.implementation

    # Both halves of this matter. The data type is what the platform promises
    # its users - a blob goes in a datastore of type blob - while the protocol
    # is whether the implementation can actually carry that out.
    holds_blobs = await implementation.get_data_type() is DataType.BLOB
    if not holds_blobs or not isinstance(implementation, BlobStorage):
        raise UnsuitableDataStoreError(datastore=store.name, wanted="blobs")

    return implementation


def get_blob(*, session: Session, project_id: UUID, key: str) -> Blob:
    """Return the blob `key` belonging to `project_id`.

    Args:
        session: The open database session.
        project_id: The project the blob belongs to.
        key: What the project calls the blob.

    Returns:
        Blob: The stored blob.

    Raises:
        ObjectNotFoundError: If that project has no blob with that key.
    """
    blob = session.exec(
        select(Blob).where(Blob.project_id == project_id, Blob.key == key)
    ).first()

    if blob is None:
        raise ObjectNotFoundError(object_type="blob", identifier=key)

    return blob


def list_blobs(*, session: Session, project_id: UUID, prefix: str | None = None) -> list[Blob]:
    """Return the blobs belonging to `project_id`, optionally under `prefix`.

    Listing reads the platform's own records rather than asking the store,
    because the records are what the policy filters and what a project is
    entitled to see. A blob uploaded around the platform is not the platform's
    to list.

    The result is not filtered by access: that is the policy's job, and the
    caller is expected to run the result past it.

    Args:
        session: The open database session.
        project_id: The project whose blobs to list.
        prefix: If given, only blobs whose key starts with it.

    Returns:
        list[Blob]: The project's blobs.
    """
    statement = select(Blob).where(Blob.project_id == project_id)
    if prefix:
        # `startswith` is rendered as a LIKE with the prefix escaped, so a key
        # containing '%' or '_' is matched literally rather than as a pattern.
        statement = statement.where(col(Blob.key).startswith(prefix, autoescape=True))

    return list(session.exec(statement).all())


async def create_blob(
    *,
    session: Session,
    project_id: UUID,
    datastore_name: str,
    key: str,
    content_type: str | None,
    description: str | None,
) -> Blob:
    """Record that a project holds a blob, and make room for it in the store.

    No bytes are written here. What this guarantees is that the project's
    namespace exists and that the key is theirs; filling it is done by the
    caller, through a URL they are handed afterwards.

    Args:
        session: The open database session.
        project_id: The project the blob will belong to.
        datastore_name: Name of the datastore that will hold it.
        key: What the project will call the blob.
        content_type: The media type the project says the blob will hold.
        description: Optional description of the blob.

    Returns:
        Blob: The stored blob.

    Raises:
        ObjectNotFoundError: If the datastore does not exist.
        UnsuitableDataStoreError: If the datastore does not hold blobs.
        DuplicateObjectError: If the project already holds that key.
        ValueError: If the key is not usable as a blob key.
        BlobProvisioningError: If the project's namespace could not be made.
    """
    validate_object_key(key=key)

    storage = await _storage_behind(session=session, datastore_name=datastore_name)

    already_there = session.exec(
        select(Blob).where(Blob.project_id == project_id, Blob.key == key)
    ).first()
    if already_there is not None:
        raise DuplicateObjectError(object_type="blob", identifier=key)

    # The namespace is the one thing that does have to exist before the record
    # does, because the URL handed out next is signed against it.
    await storage.ensure_namespace(namespace=namespace_of(project_id=project_id))

    blob = Blob(
        key=key,
        project_id=project_id,
        datastore_name=datastore_name,
        content_type=content_type,
        description=description,
    )
    session.add(blob)
    session.commit()
    session.refresh(blob)

    return blob


async def describe_blob(*, session: Session, blob: Blob) -> BlobDescription | None:
    """Return what the store holds under `blob`, or None if it holds nothing.

    Args:
        session: The open database session.
        blob: The blob to ask about.

    Returns:
        BlobDescription | None: The store's own facts, or None if nothing has
            been uploaded under the key yet.

    Raises:
        ObjectNotFoundError: If the datastore behind the blob is gone.
        UnsuitableDataStoreError: If that datastore does not hold blobs.
        BlobProvisioningError: If the store could not be asked.
    """
    storage = await _storage_behind(session=session, datastore_name=blob.datastore_name)

    return await storage.describe_blob(
        namespace=namespace_of(project_id=blob.project_id), key=blob.key
    )


async def grant_access(
    *,
    session: Session,
    blob: Blob,
    operation: BlobOperation,
    expires_in: timedelta,
) -> PresignedAccess:
    """Return a URL letting the caller perform `operation` on `blob` themselves.

    Which operation may be asked for is decided before this is called, from
    the role the caller holds. What this does is turn that decision into a
    signature the store will honour, covering one method on one key. Once it
    is handed over the platform is out of the way: it never sees the request,
    and does not need to, because the signature is the whole of what permits.

    Args:
        session: The open database session.
        blob: The blob the URL will be good for.
        operation: The one thing the URL will permit.
        expires_in: How long the URL should keep working.

    Returns:
        PresignedAccess: The signed URL, its method and its expiry.

    Raises:
        ObjectNotFoundError: If the datastore behind the blob is gone.
        UnsuitableDataStoreError: If that datastore does not hold blobs.
        BlobProvisioningError: If the URL could not be signed.
    """
    storage = await _storage_behind(session=session, datastore_name=blob.datastore_name)

    return await storage.presign(
        namespace=namespace_of(project_id=blob.project_id),
        key=blob.key,
        operation=operation,
        expires_in=expires_in,
    )


async def delete_blob(*, session: Session, blob: Blob) -> None:
    """Destroy a blob's data and forget that the project held it.

    Args:
        session: The open database session.
        blob: The blob to destroy.

    Raises:
        ObjectNotFoundError: If the datastore behind the blob is gone.
        UnsuitableDataStoreError: If that datastore does not hold blobs.
        BlobProvisioningError: If the data could not be removed, in which case
            the platform's record of the blob is kept.
    """
    storage = await _storage_behind(session=session, datastore_name=blob.datastore_name)

    await storage.delete_blob(
        namespace=namespace_of(project_id=blob.project_id), key=blob.key
    )
    session.delete(blob)
    session.commit()
