"""Endpoints for datastores.

Datastores describe the storage the whole platform is built on, so they sit
at the system level and only platform administrators may act on them. The
policy is what enforces that, and it is asked before the database is: a
datastore's name is not one of the things the answer depends on, so there is
no reason to reveal whether that name exists before knowing the caller is
allowed to ask.

The catalogue is the one endpoint here that every authenticated caller may
read, and it is deliberately not a way around any of the above: it answers
with names, data types and descriptions, and nothing that could reach the
storage. A project has to name a datastore to put a table or a blob in one,
so without it the choice the platform offers could not be made. What it
answers with is narrowed to the datastores registered as public, which is the
only thing `visibility` does anywhere. See `src.features.datastores.catalogue`.
"""

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from src.authz.policy import Action, Resource, ResourceType
from src.features.datastores import service as datastores_service
from src.features.datastores.catalogue import DataStoreCatalogueEntry, list_catalogue
from src.features.datastores.model import (
    DataStore,
    DataStoreImplementations,
    DataStoreVisibility,
)
from src.features.datastores.storage import DataStoreQueryResponse, DataType
from src.identity.caller import CurrentSubject
from src.platform.dependencies import DatabaseSession, Enforcer

__all__ = ["create_datastores_router"]


class CreateDataStoreRequest(BaseModel):
    """Request body for creating a datastore.

    `datastore` is a discriminated union: pick an implementation via its
    `implementation` tag and provide that implementation's connection fields.
    Swagger documents each variant's fields explicitly.
    """

    name: str
    description: str | None = None
    visibility: DataStoreVisibility = Field(
        default=DataStoreVisibility.PUBLIC,
        description=(
            "Whether to offer the datastore in the catalogue. Registering "
            "storage is normally an offer to build on it, so this defaults to "
            "public; `private` keeps the datastore off the list every caller "
            "reads, without making it any harder to use for somebody told its "
            "name."
        ),
    )
    datastore: DataStoreImplementations


class UpdateDataStoreVisibilityRequest(BaseModel):
    """Request body for publishing a datastore, or withdrawing it."""

    visibility: DataStoreVisibility = Field(
        description="The visibility the datastore should have from now on.",
    )


def _as_resource(*, name: str) -> Resource:
    """Describe a datastore the way the policy expects to receive it.

    A datastore carries no project and no owner: its type is enough for the
    policy to know it is part of the platform rather than of anybody's work.

    Args:
        name: Name of the datastore to describe.

    Returns:
        Resource: The datastore, as the policy sees it.
    """
    return Resource(type=ResourceType.DATASTORE, id=name)


def create_datastores_router() -> APIRouter:
    """Build the datastores router.

    Returns:
        APIRouter: The router, ready to be included in the application.
    """
    router = APIRouter(prefix="/datastores", tags=["datastores"])

    @router.get("/query", response_model=DataStoreQueryResponse)
    async def query_datastore(
        datastore: str,
        query: str,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> DataStoreQueryResponse:
        """Query the datastore named `datastore` using `query`.

        It is up to the invoker of this endpoint to know the correct
        way to query the given datastore.

        The policy is asked before the datastore is looked up, so that a
        caller who may not reach datastores at all cannot learn which names
        exist from the difference between a 403 and a 404.
        """
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.DATASTORE_QUERY,
            resource=_as_resource(name=datastore),
        )
        store = datastores_service.get_datastore(session=session, name=datastore)
        return await datastores_service.run_query(store=store, query=query)

    @router.get("/catalogue", response_model=list[DataStoreCatalogueEntry])
    async def list_datastore_catalogue(
        session: DatabaseSession,
        subject: CurrentSubject,
        data_type: DataType | None = None,
    ) -> list[DataStoreCatalogueEntry]:
        """List the storage a project may choose from, and what each holds.

        Creating a table or a blob means naming the datastore it goes in, so
        a caller who cannot learn which datastores exist cannot make that
        choice at all. This is the list they choose from, narrowed with
        `data_type` to the stores that hold the kind of object they are about
        to create.

        It answers the same way for everybody, and is the one thing about a
        datastore that is not the platform's alone. That is why no policy
        question is asked here, in the way none is asked when a caller reads
        their own account: an entry carries a name, a data type and a
        description, none of which access control protects, and a decision
        that could only ever come back "yes" would add a way for this to fail
        without adding anything it withholds. Everything that does involve the
        connection behind a datastore - registering, reading, querying,
        removing one - is below, and none of it moved.

        Being authenticated is still required, which is what `subject` is
        doing here: the platform hands its list of storage to its own callers,
        not to the internet.
        """
        return await list_catalogue(session=session, data_type=data_type)

    @router.post("/", response_model=DataStore, status_code=status.HTTP_201_CREATED)
    async def create_datastore(
        body: CreateDataStoreRequest,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> DataStore:
        """Register a new datastore with the platform.

        Registering a datastore adds storage the whole platform can be built
        on, so it is reserved for platform administrators. `visibility` is how
        an administrator says whether they are adding it for the platform or
        only for themselves.
        """
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.DATASTORE_CREATE,
            resource=_as_resource(name=body.name),
        )
        return datastores_service.create_datastore(
            session=session,
            name=body.name,
            description=body.description,
            implementation=body.datastore,
            visibility=body.visibility,
        )

    @router.get("/", response_model=list[DataStore])
    async def list_datastores(
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> list[DataStore]:
        """List the datastores the caller is allowed to see.

        The listing is filtered by the same policy that guards a direct read,
        so a caller who may not see datastores gets an empty list rather than
        a refusal. It is not filtered by visibility: this is the
        administrator's view of what the platform is built on, and a private
        datastore that nobody could find here would be a datastore nobody
        could manage.
        """
        stores = datastores_service.list_datastores(session=session)
        allowed_names = await enforcer.keep_allowed(
            subject=subject,
            action=Action.DATASTORE_READ,
            resources=[_as_resource(name=store.name) for store in stores],
        )
        return [store for store in stores if store.name in allowed_names]

    @router.get("/{datastore_name}", response_model=DataStore)
    async def get_datastore(
        datastore_name: str,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> DataStore:
        """Get the datastore with the name `datastore_name`."""
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.DATASTORE_READ,
            resource=_as_resource(name=datastore_name),
        )
        return datastores_service.get_datastore(session=session, name=datastore_name)

    @router.patch("/{datastore_name}", response_model=DataStore)
    async def update_datastore_visibility(
        datastore_name: str,
        body: UpdateDataStoreVisibilityRequest,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> DataStore:
        """Offer a datastore in the catalogue, or stop offering it.

        This is the only thing about a registered datastore that can be
        changed, because it is the only thing that says nothing about the
        storage: the connection behind a datastore is what a caller was given
        when they registered it, and re-pointing a name at different storage
        would leave every table and blob already inside it describing
        something else.

        Withdrawing a datastore takes it off the list everybody reads. It does
        not take it away from anybody: whoever already knows the name can go
        on using it, and the tables and blobs already inside it are untouched.
        """
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.DATASTORE_UPDATE,
            resource=_as_resource(name=datastore_name),
        )
        store = datastores_service.get_datastore(session=session, name=datastore_name)
        return datastores_service.set_visibility(
            session=session, store=store, visibility=body.visibility
        )

    @router.delete("/{datastore_name}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_datastore(
        datastore_name: str,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> Response:
        """Forget a datastore, leaving the storage behind it untouched."""
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.DATASTORE_DELETE,
            resource=_as_resource(name=datastore_name),
        )
        store = datastores_service.get_datastore(session=session, name=datastore_name)
        datastores_service.delete_datastore(session=session, store=store)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
