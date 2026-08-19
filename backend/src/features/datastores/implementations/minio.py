"""A datastore backed by MinIO, or anything else speaking S3.

MinIO holds blobs, so this implementation satisfies `BlobStorage` and not
`TableStorage`. A namespace becomes a bucket named after the project, which
is the same trick SQLite plays with database files and it buys the same
thing: two projects may each keep a blob called `report.parquet`, because the
two are never in the same bucket, and neither key has to be rewritten for
them not to collide.

The privilege model is where an object store differs from a database engine.
There is no statement to refuse here, so the boundary is the credential
itself: the platform holds one it never hands out, and signs from it a URL
good for one method on one key for a few minutes. A caller who may only read
receives a signature that cannot write. That is why no method here carries
bytes - putting the API in the path of the data would replace a boundary the
store enforces with one the platform would have to.

Everything the MinIO client does is synchronous, so calls that reach the
network are handed to a worker thread. Signing is not one of them: it is
local HMAC arithmetic, and only lands in a thread because the client may look
the bucket's region up the first time it signs for one.
"""

import asyncio
import re
import time
from datetime import UTC, datetime, timedelta
from functools import cached_property
from typing import Any, Literal

from minio import Minio
from minio.datatypes import Object
from minio.error import S3Error
from pydantic import (
    Field as PydanticField,
)
from pydantic import (
    SecretStr,
    SerializationInfo,
    field_serializer,
)
from urllib3.exceptions import HTTPError

from src.features.blobs.storage import (
    BlobDescription,
    BlobOperation,
    PresignedAccess,
    validate_object_key,
)
from src.features.datastores.implementations.base import DataStoreImplementationBase
from src.features.datastores.storage import DataStoreQuery, DataStoreQueryResponse, DataType
from src.platform.exceptions import (
    BlobProvisioningError,
    QueryFailedError,
    StorageError,
)

__all__ = ["MinIODataStore"]

#: What a bucket name has to look like for S3 to accept it. The platform
#: derives every bucket name it uses from a project id, so this never rejects
#: anything a caller wrote - it is here because a name that reached the store
#: unchecked would be a name the platform did not choose.
_BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")

#: The HTTP method each operation is signed for. This mapping is the whole of
#: what a signature permits, so it is kept in one place rather than decided at
#: each call site.
_METHOD_FOR: dict[BlobOperation, str] = {
    BlobOperation.DOWNLOAD: "GET",
    BlobOperation.UPLOAD: "PUT",
}

#: The S3 error codes that mean "there is nothing there", as opposed to
#: something having gone wrong. MinIO answers a missing key with one of these
#: depending on whether the bucket exists.
_ABSENT_CODES = frozenset({"NoSuchKey", "NoSuchBucket", "NoSuchObject"})

#: What a caller is shown in place of the secret key.
_REDACTED = "**********"


def _unreachable(
    *, endpoint: str, doing: str, failure: type[StorageError]
) -> StorageError:
    """Describe a store that could not be reached at all, as a platform error.

    An S3 error means the store answered and said no, and every method below
    reads one to work out what that no meant. A store that never answered -
    the host is down, the name does not resolve, the port is shut - raises out
    of the HTTP client underneath instead, and would otherwise leave the
    platform as an exception nothing had planned for. Choosing a datastore
    that is not there is an ordinary mistake to make, so it is reported as
    one rather than as the platform breaking.

    Args:
        endpoint: The store that was being reached, named in the message.
        doing: What was being attempted, phrased to follow "while".
        failure: The kind of platform error to describe it as.

    Returns:
        StorageError: The error to raise in the client's place.
    """
    return failure(f"The store at '{endpoint}' could not be reached while {doing}")


class MinIODataStore(DataStoreImplementationBase):
    """A MinIO datastore, reached over the S3 API with a platform credential.

    The credential configured here is the platform's own, and is never handed
    to a caller. It is used to provision buckets, to remove blobs, and to sign
    the short-lived URLs through which callers reach the data themselves.
    """

    implementation: Literal["minio"] = "minio"
    endpoint: str = PydanticField(
        description=(
            "Host and optional port of the MinIO server, without a scheme. "
            "The scheme is decided by `secure`."
        ),
        examples=["minio.example.com:9000", "localhost:9000"],
    )
    access_key: str = PydanticField(
        description="Access key of the platform's own MinIO credential.",
    )
    secret_key: SecretStr = PydanticField(
        description=(
            "Secret key of the platform's own MinIO credential. It is stored "
            "with the datastore and is never included in an API response."
        ),
    )
    secure: bool = PydanticField(
        default=True,
        description="Whether to reach the server over HTTPS. Only turn this off locally.",
    )
    region: str | None = PydanticField(
        default=None,
        description="Region to create buckets in, if the server cares about one.",
    )
    presigned_url_expiry_seconds: int = PydanticField(
        default=900,
        gt=0,
        le=7 * 24 * 60 * 60,
        description=(
            "How long a signed URL stays valid. Short is safer: the URL is the "
            "whole of the authorization, so anybody holding it holds the access "
            "until it expires. S3 will not sign for longer than seven days."
        ),
    )

    @field_serializer("secret_key", when_used="always")
    def _reveal_secret_key_only_to_the_database(
        self, value: SecretStr, info: SerializationInfo
    ) -> str:
        """Write the secret out in the clear only when the database asked.

        `SecretStr` already keeps the secret out of a `repr`, a log line and
        any exception that interpolates this model, which is what stops it
        escaping by accident. What it cannot do on its own is be persisted:
        left to itself it masks in JSON mode too, and the platform would
        store the mask and never reconnect. So this serializer inverts the
        default for exactly one destination - the dump in `src.features.datastores.model`
        that writes the row, which says so - and masks for every other.

        Args:
            value: The secret key, still wrapped.
            info: The serialization context, carrying who asked.

        Returns:
            str: The secret key, or a fixed mask in its place.
        """
        context = info.context or {}
        return value.get_secret_value() if context.get("reveal_secrets") else _REDACTED

    @cached_property
    def _client(self) -> Minio:
        """Return the MinIO client, built once per instance.

        Returns:
            Minio: A client authenticated with the platform's credential.
        """
        return Minio(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key.get_secret_value(),
            secure=self.secure,
            region=self.region,
        )

    async def get_data_type(self) -> DataType:
        return DataType.BLOB

    @staticmethod
    def _bucket_for(*, namespace: str) -> str:
        """Return the bucket holding `namespace`, checking it is a usable name.

        Args:
            namespace: The namespace whose bucket is wanted.

        Returns:
            str: The bucket name.

        Raises:
            BlobProvisioningError: If the namespace could not be a bucket name.
        """
        if _BUCKET_NAME.fullmatch(namespace) is None:
            raise BlobProvisioningError(
                f"'{namespace}' cannot be used as a bucket name: S3 wants 3 to "
                "63 characters of lowercase letters, digits, dots and dashes, "
                "starting and ending with a letter or digit."
            )

        return namespace

    async def query(self, query: DataStoreQuery) -> DataStoreQueryResponse:
        """List what the store holds, which is what querying a blob store means.

        There is no query language here, so the statement is read as a place
        to look: empty lists the buckets, `<bucket>` lists that bucket, and
        `<bucket>/<prefix>` lists the part of it under `prefix`. Only platform
        administrators reach this, and it sees every project's bucket, which
        is why a project's own blobs are reached through the blob endpoints
        instead.

        Args:
            query: Where to look, as described above.

        Returns:
            DataStoreQueryResponse: What was found, and how long looking took.

        Raises:
            QueryFailedError: If the store could not be listed.
        """
        query_start_time = time.time()
        bucket, _, prefix = query.query.strip().partition("/")

        try:
            if not bucket:
                buckets = await asyncio.to_thread(self._client.list_buckets)
                data: Any = [
                    {"bucket": found.name, "creation_date": found.creation_date}
                    for found in buckets
                ]
                metadata = {"listed": "buckets"}
            else:
                objects = await asyncio.to_thread(
                    lambda: list(
                        self._client.list_objects(
                            bucket_name=bucket,
                            prefix=prefix or None,
                            recursive=True,
                        )
                    )
                )
                data = [
                    self._describe(key=found.object_name or "", found=found).model_dump()
                    for found in objects
                ]
                metadata = {"listed": "blobs", "bucket": bucket, "prefix": prefix}
        except S3Error as error:
            raise QueryFailedError(f"The store could not be listed: {error}") from error
        except HTTPError as error:
            raise _unreachable(
                endpoint=self.endpoint,
                doing="listing what it holds",
                failure=QueryFailedError,
            ) from error

        return DataStoreQueryResponse(
            data=data,
            metadata=metadata,
            latency=time.time() - query_start_time,
        )

    @staticmethod
    def _describe(*, key: str, found: Object) -> BlobDescription:
        """Turn what the client returned into the platform's own description.

        Args:
            key: The key that was asked about.
            found: The object the client handed back.

        Returns:
            BlobDescription: The same facts, in the platform's vocabulary.
        """
        return BlobDescription(
            key=key,
            size=found.size or 0,
            etag=found.etag,
            last_modified=found.last_modified,
            content_type=found.content_type,
        )

    async def ensure_namespace(self, *, namespace: str) -> None:
        """Create this project's bucket if it is not already there.

        Args:
            namespace: The project's namespace.

        Raises:
            BlobProvisioningError: If the bucket could not be created.
        """
        bucket = self._bucket_for(namespace=namespace)

        try:
            if await asyncio.to_thread(self._client.bucket_exists, bucket_name=bucket):
                return

            await asyncio.to_thread(
                self._client.make_bucket, bucket_name=bucket, location=self.region
            )
        except S3Error as error:
            # Two callers creating their project's first blob at once both see
            # the bucket missing and both try to make it. The loser is told the
            # bucket is already there, which is the outcome it wanted.
            if error.code in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                return

            raise BlobProvisioningError(
                f"The namespace '{namespace}' could not be created: {error}"
            ) from error
        except HTTPError as error:
            raise _unreachable(
                endpoint=self.endpoint,
                doing=f"creating the namespace '{namespace}'",
                failure=BlobProvisioningError,
            ) from error

    async def delete_blob(self, *, namespace: str, key: str) -> None:
        """Remove the blob `key`, and say nothing if it was not there.

        Args:
            namespace: The project's namespace.
            key: Key of the blob to remove.

        Raises:
            BlobProvisioningError: If the blob could not be removed.
        """
        bucket = self._bucket_for(namespace=namespace)
        validate_object_key(key=key)

        try:
            await asyncio.to_thread(
                self._client.remove_object, bucket_name=bucket, object_name=key
            )
        except S3Error as error:
            # A record whose bytes are already gone still has to be deletable,
            # or the platform would be left describing something nobody can
            # remove.
            if error.code in _ABSENT_CODES:
                return

            raise BlobProvisioningError(
                f"The blob '{key}' could not be removed: {error}"
            ) from error
        except HTTPError as error:
            raise _unreachable(
                endpoint=self.endpoint,
                doing=f"removing the blob '{key}'",
                failure=BlobProvisioningError,
            ) from error

    async def describe_blob(self, *, namespace: str, key: str) -> BlobDescription | None:
        """Return what the store holds under `key`, or None if it holds nothing.

        Args:
            namespace: The project's namespace.
            key: Key of the blob to describe.

        Returns:
            BlobDescription | None: The blob's facts, or None if nothing has
                been uploaded under that key yet.

        Raises:
            BlobProvisioningError: If the store could not be asked.
        """
        bucket = self._bucket_for(namespace=namespace)
        validate_object_key(key=key)

        try:
            found = await asyncio.to_thread(
                self._client.stat_object, bucket_name=bucket, object_name=key
            )
        except S3Error as error:
            if error.code in _ABSENT_CODES:
                return None

            raise BlobProvisioningError(
                f"The blob '{key}' could not be described: {error}"
            ) from error
        except HTTPError as error:
            raise _unreachable(
                endpoint=self.endpoint,
                doing=f"describing the blob '{key}'",
                failure=BlobProvisioningError,
            ) from error

        return self._describe(key=key, found=found)

    async def presign(
        self,
        *,
        namespace: str,
        key: str,
        operation: BlobOperation,
        expires_in: timedelta,
    ) -> PresignedAccess:
        """Sign a URL good for `operation` on `key`, and for nothing else.

        The signature covers the method, the bucket and the key together, so
        a URL for reading one blob cannot be turned into a URL for writing it,
        nor pointed at a blob belonging to another project. MinIO is what
        refuses those, and it does so without the platform seeing the request.

        Args:
            namespace: The project's namespace.
            key: Key of the only blob the URL may be used on.
            operation: The one thing the URL may be used to do.
            expires_in: How long the signature should remain valid.

        Returns:
            PresignedAccess: The signed URL, its method and its expiry.

        Raises:
            BlobProvisioningError: If the URL could not be signed.
        """
        bucket = self._bucket_for(namespace=namespace)
        validate_object_key(key=key)
        method = _METHOD_FOR[operation]

        # Whoever configured this datastore and whoever asked for the URL both
        # get a say, and the shorter answer wins. A caller cannot talk the
        # store into signing for longer than it was set up to.
        lifetime = min(expires_in, timedelta(seconds=self.presigned_url_expiry_seconds))

        try:
            url = await asyncio.to_thread(
                self._client.get_presigned_url,
                method=method,
                bucket_name=bucket,
                object_name=key,
                expires=lifetime,
            )
        except (S3Error, ValueError) as error:
            raise BlobProvisioningError(
                f"Access to the blob '{key}' could not be signed: {error}"
            ) from error
        except HTTPError as error:
            # Signing is local arithmetic, but the client may go and look the
            # bucket's region up the first time it signs for one.
            raise _unreachable(
                endpoint=self.endpoint,
                doing=f"signing access to the blob '{key}'",
                failure=BlobProvisioningError,
            ) from error

        return PresignedAccess(
            url=url,
            method=method,
            expires_at=datetime.now(tz=UTC) + lifetime,
        )
