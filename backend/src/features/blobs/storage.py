"""What storage that holds blobs can do, and how access to one is granted.

A datastore implementation describes *how* to reach some storage. This module
describes what it means for one to hold *blobs*: an implementation that does
satisfies `BlobStorage`, one that holds something else simply does not, and
the service layer asks before it tries.

`src.features.tables.storage` draws its boundary with privilege, because
there is a statement for an engine to refuse. Here there is no statement, so
the boundary is drawn by the credential instead: the platform signs a URL
good for one HTTP method on one key in one bucket, and the object store is
what turns away anything else. A caller who may only read is handed a
signature that cannot write, rather than a request that gets inspected.
"""

import re
from datetime import datetime, timedelta
from enum import StrEnum, auto
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

__all__ = [
    "BlobDescription",
    "BlobOperation",
    "BlobStorage",
    "PresignedAccess",
    "validate_object_key",
]

#: What one segment of a blob key may be built from. A key is a path, and the
#: platform splits it on '/' before checking each piece against this, which is
#: what keeps the rule readable: the interesting cases are all about the
#: segments, not about the string as a whole.
_KEY_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")

#: The longest a blob key may be. S3 puts the limit at 1024 bytes of UTF-8,
#: and since every character a key may contain is one byte here, counting
#: characters is counting bytes.
_MAX_KEY_LENGTH = 1024


def validate_object_key(*, key: str) -> str:
    """Return `key` if it is usable as a blob key, and raise if not.

    A key is the whole of a blob's name, and the only hierarchy blobs have:
    `reports/2026/q1.parquet` is one key, not a folder holding a file. What
    this refuses is therefore not punctuation for its own sake but the shapes
    that stop a key meaning one fixed place - a leading slash, an empty
    segment, or a `..` that would walk the key somewhere else once it is
    resolved against a URL.

    Args:
        key: The key to check.

    Returns:
        str: The key, unchanged.

    Raises:
        ValueError: If the key could be read as anything but one blob's name.
    """
    if not key:
        raise ValueError("A blob key cannot be empty.")

    if len(key) > _MAX_KEY_LENGTH:
        raise ValueError(
            f"A blob key may be at most {_MAX_KEY_LENGTH} characters long, and "
            f"this one is {len(key)}."
        )

    segments = key.split("/")
    for segment in segments:
        if segment in {"", ".", ".."}:
            raise ValueError(
                f"'{key}' is not a usable blob key: it must not begin or end "
                "with '/', contain an empty segment, or contain '.' or '..'."
            )

        if _KEY_SEGMENT.fullmatch(segment) is None:
            raise ValueError(
                f"'{segment}' is not a usable part of a blob key: each part "
                "between slashes must start with a letter or digit, continue "
                "with letters, digits, dots, dashes or underscores, and be at "
                "most 255 characters long."
            )

    return key


class BlobOperation(StrEnum):
    """The one thing a signed URL is good for.

    A signature covers a single operation on a single key, so this is not a
    description of what a caller may generally do - it is the whole of what
    the URL being handed out can be used for. Deleting is deliberately absent:
    a blob's data and the platform's record of it are removed together, which
    a URL handed to a client could never guarantee.
    """

    #: Read the blob's bytes.
    DOWNLOAD = auto()

    #: Replace the blob's bytes.
    UPLOAD = auto()


class BlobDescription(BaseModel):
    """What the object store knows about a blob that the platform does not.

    The platform records that a blob exists and who it belongs to. Its size,
    its checksum and when it last changed are facts about the bytes, so they
    are asked of the store when wanted rather than mirrored into a row that
    would go stale the moment somebody uploaded through a signed URL.
    """

    key: str = Field(description="The blob's key within its project's namespace.")
    size: int = Field(description="Size of the blob in bytes.")
    etag: str | None = Field(
        default=None, description="The store's checksum of the current contents."
    )
    last_modified: datetime | None = Field(
        default=None, description="When the blob's contents last changed."
    )
    content_type: str | None = Field(
        default=None, description="The media type the blob was uploaded with."
    )


class PresignedAccess(BaseModel):
    """A URL that carries its own authorization, and when it stops working.

    The expiry is returned alongside the URL because it is the caller's to
    respect: they were handed something that stops working, and nothing will
    tell them when it does except this.
    """

    url: str = Field(description="The signed URL to send the request to.")
    method: str = Field(
        description="The HTTP method the signature covers. Any other is refused.",
        examples=["GET", "PUT"],
    )
    expires_at: datetime = Field(description="When the signature stops being accepted.")


@runtime_checkable
class BlobStorage(Protocol):
    """Storage that holds unstructured blobs, kept apart by namespace.

    Blobs have no hierarchy of their own. A key may read like a path, and the
    store will happily list by prefix, but `reports/q1.parquet` is one blob
    with one name rather than a file inside a folder. Nothing here creates or
    removes a container, because there is none to create.

    `namespace` means the same as it does in `TableStorage`: the part of this
    datastore belonging to one project. How that is realised is the
    implementation's business, and no caller ever names one.

    Note what is missing. There is no method to read or write a blob's bytes,
    because the platform never carries them: `presign` hands back a URL the
    caller uses against the store directly. That is the same bargain
    `TableStorage` makes by connecting at a privilege - the boundary is
    enforced by the thing holding the data, not by the platform inspecting a
    request.
    """

    async def ensure_namespace(self, *, namespace: str) -> None:
        """Make sure `namespace` exists, creating it if it does not.

        This runs at the privilege that may create, which is why it is a
        method here rather than something a signed URL could accomplish.
        Implementations must tolerate being called when the namespace already
        exists, because it is called before every blob is created.

        Args:
            namespace: The part of the datastore to bring into existence.

        Raises:
            BlobProvisioningError: If the namespace could not be created.
        """
        ...

    async def delete_blob(self, *, namespace: str, key: str) -> None:
        """Destroy the blob `key` in `namespace`.

        Deleting goes through the platform rather than through a signed URL so
        that the bytes and the record of them are removed in one act.
        Implementations must not fail when the blob is already absent: the
        platform's record can outlive the bytes, and deleting must still work.

        Args:
            namespace: The part of the datastore the blob belongs in.
            key: Key of the blob to destroy.

        Raises:
            BlobProvisioningError: If the blob could not be removed.
        """
        ...

    async def describe_blob(self, *, namespace: str, key: str) -> BlobDescription | None:
        """Return what the store knows about `key`, or None if it holds nothing.

        None is an ordinary answer rather than an error. A blob is recorded
        before it is uploaded, so a record with no bytes behind it yet is a
        normal state and the caller is told so plainly.

        Args:
            namespace: The part of the datastore the blob belongs in.
            key: Key of the blob to describe.

        Returns:
            BlobDescription | None: What the store holds, or None if nothing
                has been uploaded under that key.

        Raises:
            BlobProvisioningError: If the store could not be asked.
        """
        ...

    async def presign(
        self,
        *,
        namespace: str,
        key: str,
        operation: BlobOperation,
        expires_in: timedelta,
    ) -> PresignedAccess:
        """Return a URL good for `operation` on `key`, and nothing else.

        The signature must cover one method, one namespace and one key.
        Implementations must not return a credential that could be turned on
        another blob, because this URL leaves the platform and the platform
        will not see the request it is used for.

        Args:
            namespace: The part of the datastore the blob belongs in.
            key: Key of the only blob the URL may be used on.
            operation: The one thing the URL may be used to do.
            expires_in: How long the signature should remain valid.

        Returns:
            PresignedAccess: The signed URL, its method and its expiry.

        Raises:
            BlobProvisioningError: If the URL could not be signed.
        """
        ...
