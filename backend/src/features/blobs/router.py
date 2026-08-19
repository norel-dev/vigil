"""Endpoints for the blobs a project holds.

Blobs sit under a project, so they live under it in the URL too, and the role
the caller holds in that project is what decides everything below.

Two things here are worth reading before the code. First, a key may contain
slashes, so it is captured as a path rather than a path segment: everything
after `/blobs/` is the key, and it is one name rather than a route into
anything. Second, the platform never carries a blob's bytes. The access
endpoint answers with a URL the caller uses against the store directly, which
is the same bargain the query endpoint makes for tables - the boundary is
enforced by whatever holds the data, not by the platform inspecting a
request. It follows that a signed URL cannot be taken back once handed out,
which is why they are signed for minutes rather than days.
"""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field, field_validator

from src.authz.policy import Action, Resource, ResourceType
from src.features.blobs import service as blobs_service
from src.features.blobs.model import Blob
from src.features.blobs.storage import (
    BlobDescription,
    BlobOperation,
    PresignedAccess,
    validate_object_key,
)
from src.features.projects import service as projects_service
from src.identity.caller import CurrentSubject
from src.platform.dependencies import DatabaseSession, Enforcer

__all__ = ["create_blobs_router"]

#: How long a signed URL is asked to last. This is what the platform requests,
#: not necessarily what it gets: a datastore configured to sign for less will
#: sign for less, because the shorter of the two is always the safer one.
_ACCESS_LIFETIME = timedelta(minutes=15)


class CreateBlobRequest(BaseModel):
    """Request body for recording a blob."""

    key: str = Field(
        description=(
            "What the project will call this blob. Slashes are part of the "
            "name rather than folders, so nothing has to be created first."
        ),
        examples=["reports/2026/q1.parquet"],
    )
    datastore: str = Field(
        description=(
            "Name of the datastore that will hold the blob. It must be a "
            "datastore that holds blobs."
        ),
    )
    content_type: str | None = Field(
        default=None,
        description="The media type the blob will hold, recorded as told.",
        examples=["application/octet-stream"],
    )
    description: str | None = Field(
        default=None, description="What the blob is for."
    )

    @field_validator("key")
    @classmethod
    def _check_key(cls, value: str) -> str:
        """Reject keys that would not name one fixed blob.

        Args:
            value: The proposed blob key.

        Returns:
            str: The key, unchanged.

        Raises:
            ValueError: If the key is not usable as a blob key.
        """
        return validate_object_key(key=value)


class BlobView(BaseModel):
    """A blob as a caller sees it: the record, plus what the store holds.

    The two halves are reported separately on purpose. The record is the
    platform's, and always exists; `stored` is the store's answer at the
    moment of asking, and is null when nothing has been uploaded under the key
    yet. Collapsing them would leave a caller unable to tell an empty blob
    from one that was never filled.
    """

    blob: Blob
    stored: BlobDescription | None = Field(
        default=None,
        description=(
            "What the object store holds under this key, or null if nothing "
            "has been uploaded yet."
        ),
    )


class CreatedBlob(BaseModel):
    """A newly recorded blob, together with the way to put data in it."""

    blob: Blob
    upload: PresignedAccess = Field(
        description=(
            "A URL to send the blob's contents to. It is good for one PUT of "
            "this one key and expires shortly, so ask again if it lapses."
        ),
    )


class BlobAccessRequest(BaseModel):
    """Request body for asking to reach a blob's contents."""

    operation: BlobOperation = Field(
        description=(
            "What the caller means to do. Downloading takes the same rights as "
            "reading the project; uploading takes the rights of an editor."
        ),
    )


def _as_resource(*, project_id: UUID, identifier: str) -> Resource:
    """Describe a blob the way the policy expects to receive it.

    Args:
        project_id: The project that governs the blob.
        identifier: How the caller refers to the blob.

    Returns:
        Resource: The blob, as the policy sees it.
    """
    return Resource(type=ResourceType.BLOB, id=identifier, project_id=project_id)


#: The permission each operation takes. Keeping this beside the request model
#: rather than inside the endpoint is what stops a new operation being added
#: without somebody deciding what it costs.
_ACTION_FOR: dict[BlobOperation, Action] = {
    BlobOperation.DOWNLOAD: Action.BLOB_DOWNLOAD,
    BlobOperation.UPLOAD: Action.BLOB_UPLOAD,
}


def create_blobs_router() -> APIRouter:
    """Build the blobs router.

    Returns:
        APIRouter: The router, ready to be included in the application.
    """
    router = APIRouter(prefix="/projects/{project_id}/blobs", tags=["blobs"])

    @router.post("/", response_model=CreatedBlob, status_code=status.HTTP_201_CREATED)
    async def create_blob(
        project_id: UUID,
        body: CreateBlobRequest,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> CreatedBlob:
        """Claim a key in a datastore and give the blob to this project.

        Creating a blob claims a name inside a datastore the whole platform
        shares, and is therefore reserved for the project's owner. No data is
        written here: the response carries a URL to upload through, and until
        it is used the blob is recorded but empty.
        """
        projects_service.get_project(session=session, project_id=project_id)
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.BLOB_CREATE,
            resource=_as_resource(project_id=project_id, identifier=body.key),
        )

        blob = await blobs_service.create_blob(
            session=session,
            project_id=project_id,
            datastore_name=body.datastore,
            key=body.key,
            content_type=body.content_type,
            description=body.description,
        )
        upload = await blobs_service.grant_access(
            session=session,
            blob=blob,
            operation=BlobOperation.UPLOAD,
            expires_in=_ACCESS_LIFETIME,
        )

        return CreatedBlob(blob=blob, upload=upload)

    @router.get("/", response_model=list[Blob])
    async def list_blobs(
        project_id: UUID,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
        prefix: str | None = None,
    ) -> list[Blob]:
        """List the blobs of this project that the caller may see.

        `prefix` narrows the listing to keys beginning with it, which is what
        the slashes in a key are good for: asking for `reports/` gets the
        blobs named as though they were in a folder, without there being one.
        """
        blobs = blobs_service.list_blobs(
            session=session, project_id=project_id, prefix=prefix
        )
        allowed_ids = await enforcer.keep_allowed(
            subject=subject,
            action=Action.BLOB_READ,
            resources=[
                _as_resource(project_id=project_id, identifier=str(blob.id))
                for blob in blobs
            ],
        )
        return [blob for blob in blobs if str(blob.id) in allowed_ids]

    @router.get("/{key:path}", response_model=BlobView)
    async def get_blob(
        project_id: UUID,
        key: str,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> BlobView:
        """Read the platform's record of one blob, and what the store holds.

        This describes the blob, not its contents: the bytes are reached
        through the access endpoint below.
        """
        blob = blobs_service.get_blob(session=session, project_id=project_id, key=key)
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.BLOB_READ,
            resource=_as_resource(project_id=project_id, identifier=str(blob.id)),
        )

        return BlobView(
            blob=blob,
            stored=await blobs_service.describe_blob(session=session, blob=blob),
        )

    @router.post("/{key:path}/access", response_model=PresignedAccess)
    async def grant_blob_access(
        project_id: UUID,
        key: str,
        body: BlobAccessRequest,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> PresignedAccess:
        """Hand back a URL letting the caller reach this blob's contents.

        The caller says what they mean to do, and that is what is asked of the
        policy: downloading and uploading are separate permissions, so a
        viewer is refused an upload URL outright rather than being handed one
        that fails later. What comes back is signed for that one method on
        this one key, and expires within minutes - a signature cannot be
        withdrawn, so it is made not to last.
        """
        blob = blobs_service.get_blob(session=session, project_id=project_id, key=key)
        await enforcer.ensure_allowed(
            subject=subject,
            action=_ACTION_FOR[body.operation],
            resource=_as_resource(project_id=project_id, identifier=str(blob.id)),
        )

        return await blobs_service.grant_access(
            session=session,
            blob=blob,
            operation=body.operation,
            expires_in=_ACCESS_LIFETIME,
        )

    @router.delete("/{key:path}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_blob(
        project_id: UUID,
        key: str,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> Response:
        """Destroy a blob and its contents.

        Deleting goes through the platform rather than through a signed URL,
        because the data and the record of it have to go together: a URL handed
        to a client could remove one and leave the other.
        """
        blob = blobs_service.get_blob(session=session, project_id=project_id, key=key)
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.BLOB_DELETE,
            resource=_as_resource(project_id=project_id, identifier=str(blob.id)),
        )

        await blobs_service.delete_blob(session=session, blob=blob)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
