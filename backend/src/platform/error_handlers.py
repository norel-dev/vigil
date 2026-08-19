"""Translation of platform errors into HTTP responses.

Handlers below are the only place that decides what an error looks like on
the wire, which is why no other module raises `HTTPException`.

A failure to reach the policy engine is answered with 503 rather than 403:
the caller is not being told they may not do something, they are being told
the platform could not work out whether they may. Either way the action does
not happen.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from src.platform.exceptions import (
    BlobProvisioningError,
    DuplicateObjectError,
    InvalidApiKeyError,
    ObjectNotFoundError,
    PermissionDeniedError,
    PolicyDecisionPointError,
    QueryFailedError,
    QueryRefusedError,
    TableProvisioningError,
    UnsuitableDataStoreError,
)

__all__ = ["register_error_handlers"]


def register_error_handlers(*, app: FastAPI) -> None:
    """Teach `app` how to answer the platform's errors.

    Args:
        app: The application to register the handlers on.
    """

    @app.exception_handler(InvalidApiKeyError)
    async def _handle_invalid_api_key(_: Request, error: InvalidApiKeyError) -> JSONResponse:
        """Answer an unusable key with 401 and a challenge."""
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": str(error)},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(PermissionDeniedError)
    async def _handle_permission_denied(
        _: Request, error: PermissionDeniedError
    ) -> JSONResponse:
        """Answer a policy denial with 403 and the policy's own explanation."""
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "detail": str(error),
                "action": error.action,
                "resource": error.resource,
                "reason": error.reason,
            },
        )

    @app.exception_handler(PolicyDecisionPointError)
    async def _handle_policy_engine_down(
        _: Request, error: PolicyDecisionPointError
    ) -> JSONResponse:
        """Answer an unusable policy engine with 503, having granted nothing."""
        logger.error("Policy decision point failure: {}", error)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Could not evaluate the access policy right now"},
        )

    @app.exception_handler(ObjectNotFoundError)
    async def _handle_not_found(_: Request, error: ObjectNotFoundError) -> JSONResponse:
        """Answer a missing object with 404."""
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(error)},
        )

    @app.exception_handler(DuplicateObjectError)
    async def _handle_duplicate(_: Request, error: DuplicateObjectError) -> JSONResponse:
        """Answer a name that is already taken with 409."""
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(error)},
        )

    @app.exception_handler(QueryRefusedError)
    async def _handle_query_refused(_: Request, error: QueryRefusedError) -> JSONResponse:
        """Answer a statement the engine refused with 403.

        This is a refusal like any other, even though it came from the
        database rather than from the policy: the caller asked to do more than
        the privilege they hold, and was told no.
        """
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": str(error)},
        )

    @app.exception_handler(QueryFailedError)
    async def _handle_query_failed(_: Request, error: QueryFailedError) -> JSONResponse:
        """Answer a statement that could not run with 400 and the engine's words."""
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(error)},
        )

    @app.exception_handler(UnsuitableDataStoreError)
    async def _handle_unsuitable_datastore(
        _: Request, error: UnsuitableDataStoreError
    ) -> JSONResponse:
        """Answer a datastore that cannot hold what was asked of it with 400."""
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(error)},
        )

    @app.exception_handler(BlobProvisioningError)
    async def _handle_blob_provisioning_failure(
        _: Request, error: BlobProvisioningError
    ) -> JSONResponse:
        """Answer an object store that would not do as asked with 502.

        This is not the caller being refused and not the platform being
        broken: it is the storage behind the datastore they chose failing to
        answer, or answering with a no of its own. 502 says that plainly,
        where a 500 would have claimed the fault was here.

        What this does not cover is an upload or a download, because those
        never reach the platform. A caller whose signed URL is refused hears
        it from the store directly.
        """
        logger.error("Blob provisioning failure: {}", error)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": str(error)},
        )

    @app.exception_handler(TableProvisioningError)
    async def _handle_provisioning_failure(
        _: Request, error: TableProvisioningError
    ) -> JSONResponse:
        """Answer storage that would not be shaped as asked with 400.

        The usual cause is the column definitions the caller supplied, which
        the platform passes to the engine without trying to understand them,
        so the engine's own explanation is handed back rather than replaced.
        """
        logger.error("Table provisioning failure: {}", error)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(error)},
        )
