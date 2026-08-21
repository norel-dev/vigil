"""Endpoints for the tables a project holds.

Tables sit under a project, so they live under it in the URL too, and the
role the caller holds in that project is what decides everything below.

The query endpoint is the unusual one. Everywhere else a denial ends the
request, but here the policy is asked what the caller may do rather than
whether they may proceed: somebody who cannot write to a table may still be
allowed to read it. The answer picks the privilege the platform connects to
the datastore with, and from that point the engine is what enforces it. The
statement itself is never read by the platform - not to classify it, not to
validate it - because a caller who can get a statement past a reader would
have got past the only thing protecting the table.
"""

from uuid import UUID

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field, field_validator

from src.authz.policy import Action, Resource, ResourceType
from src.features.datastores.storage import DataStoreQueryResponse
from src.features.projects import service as projects_service
from src.features.tables import service as tables_service
from src.features.tables.model import Table
from src.features.tables.storage import (
    ColumnDefinition,
    QueryPrivilege,
    validate_identifier,
)
from src.identity.caller import CurrentSubject
from src.platform.dependencies import DatabaseSession, Enforcer

__all__ = ["create_tables_router"]


class CreateTableRequest(BaseModel):
    """Request body for creating a table."""

    name: str = Field(
        description=(
            "What the project will call this table, and what its members will "
            "write in their SQL. It must be a plain SQL identifier."
        ),
        examples=["customers"],
    )

    datastore: str = Field(
        description=(
            "Name of the datastore that will hold the table. It must be a "
            "datastore that holds tables."
        ),
    )
    columns: list[ColumnDefinition] = Field(
        min_length=1,
        description="The columns the table should have, in order.",
    )
    description: str | None = Field(
        default=None, description="What the table is for."
    )

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        """Reject table names SQL could not take.

        The caller writes this name in their own statements, so it reaches the
        engine as an identifier and has to be usable as one.

        Args:
            value: The proposed table name.

        Returns:
            str: The name, unchanged.

        Raises:
            ValueError: If the name is not a usable identifier.
        """
        return validate_identifier(name=value, kind="table name")


class TableQueryRequest(BaseModel):
    """Request body for running a statement against a table."""

    query: str = Field(
        description=(
            "One statement, in the dialect the datastore speaks. It may read "
            "and change this table, and alter its shape, but it may not "
            "create or drop anything, and it may not reach another table."
        ),
        examples=["SELECT * FROM customers"],
    )


def _as_resource(*, project_id: UUID, identifier: str) -> Resource:
    """Describe a table the way the policy expects to receive it.

    Args:
        project_id: The project that governs the table.
        identifier: How the caller refers to the table.

    Returns:
        Resource: The table, as the policy sees it.
    """
    return Resource(type=ResourceType.TABLE, id=identifier, project_id=project_id)


def create_tables_router() -> APIRouter:
    """Build the tables router.

    Returns:
        APIRouter: The router, ready to be included in the application.
    """
    router = APIRouter(prefix="/projects/{project_id}/tables", tags=["tables"])

    @router.post("/", response_model=Table, status_code=status.HTTP_201_CREATED)
    async def create_table(
        project_id: UUID,
        body: CreateTableRequest,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> Table:
        """Create a table in a datastore and give it to this project.

        Creating a table claims storage inside a datastore the whole platform
        shares, and is therefore reserved for the project's owner. The table's
        name inside the datastore is generated rather than taken from the
        request, because that datastore holds other projects' tables too.
        """
        projects_service.get_project(session=session, project_id=project_id)
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.TABLE_CREATE,
            resource=_as_resource(project_id=project_id, identifier=body.name),
        )

        return await tables_service.create_table(
            session=session,
            project_id=project_id,
            datastore_name=body.datastore,
            name=body.name,
            description=body.description,
            columns=body.columns,
        )

    @router.get("/", response_model=list[Table])
    async def list_tables(
        project_id: UUID,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> list[Table]:
        """List the tables of this project that the caller may see."""
        tables = tables_service.list_tables(session=session, project_id=project_id)
        allowed_ids = await enforcer.keep_allowed(
            subject=subject,
            action=Action.TABLE_READ,
            resources=[
                _as_resource(project_id=project_id, identifier=str(table.id))
                for table in tables
            ],
        )
        return [table for table in tables if str(table.id) in allowed_ids]

    @router.get("/{table_name}", response_model=Table)
    async def get_table(
        project_id: UUID,
        table_name: str,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> Table:
        """Read the platform's record of one table.

        This describes the table, not what is in it: the rows are reached
        through the query endpoint below.
        """
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.TABLE_READ,
            resource=_as_resource(project_id=project_id, identifier=table_name),
        )
        return tables_service.get_table(
            session=session, project_id=project_id, name=table_name
        )

    @router.post("/{table_name}/query", response_model=DataStoreQueryResponse)
    async def query_table(
        project_id: UUID,
        table_name: str,
        body: TableQueryRequest,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> DataStoreQueryResponse:
        """Run one statement against a table.

        The caller's role decides how much the statement is allowed to do: a
        caller the policy grants `table.write` connects with a privilege that
        can also change rows and alter the table, and everybody else who may
        reach it at all connects read-only. Neither privilege can create or
        drop anything, or touch a table other than this one, and it is the
        database engine that refuses - not a check over the statement text.
        """
        # The policy is asked before the table is looked up, so that a caller
        # who may not reach this project cannot learn which table names exist
        # in it from the difference between a 403 and a 404. The resource id is
        # the name the caller supplied, which is all the policy needs at
        # project scope, and reveals nothing back to them they did not send.
        resource = _as_resource(project_id=project_id, identifier=table_name)

        may_write = await enforcer.is_allowed(
            subject=subject, action=Action.TABLE_WRITE, resource=resource
        )
        if not may_write:
            # Not being allowed to write is not the end of the request, but
            # not being allowed to read is: this is what refuses outsiders,
            # with the policy's own explanation.
            await enforcer.ensure_allowed(
                subject=subject, action=Action.TABLE_QUERY, resource=resource
            )

        table = tables_service.get_table(
            session=session, project_id=project_id, name=table_name
        )
        return await tables_service.run_query(
            session=session,
            table=table,
            query=body.query,
            privilege=QueryPrivilege.READ_WRITE if may_write else QueryPrivilege.READ_ONLY,
        )

    @router.delete("/{table_name}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_table(
        project_id: UUID,
        table_name: str,
        session: DatabaseSession,
        enforcer: Enforcer,
        subject: CurrentSubject,
    ) -> Response:
        """Destroy a table and everything in it.

        Unlike deleting a datastore, this does not only forget a record: the
        platform created this table, so deleting it drops the table and the
        rows in it for good.
        """
        await enforcer.ensure_allowed(
            subject=subject,
            action=Action.TABLE_DELETE,
            resource=_as_resource(project_id=project_id, identifier=table_name),
        )
        table = tables_service.get_table(
            session=session, project_id=project_id, name=table_name
        )
        await tables_service.delete_table(session=session, table=table)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
