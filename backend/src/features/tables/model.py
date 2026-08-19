"""Tables: the first thing a project actually holds.

A table is the platform's record of a structured table living inside some
datastore. It is deliberately thin. The shape of the data - which columns
exist and what they hold - is the engine's to know, not the platform's, and
is asked of the engine rather than mirrored here; a caller who alters their
table would otherwise leave this record describing something that no longer
exists.

There is only one name, and it is the one the project chose. A datastore
holds each project's tables in a namespace of its own, so a name only has to
be unique within its project, and the name a caller writes in their SQL is
the name they asked for. Because that name reaches the engine, it has to be
a plain SQL identifier, which is checked before a table is created.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, UniqueConstraint

__all__ = ["Table"]


class Table(SQLModel, table=True):
    """A structured table belonging to a project, held by a datastore.

    A table has no owner column for the same reason a project has none: it
    sits at the project level, so who may touch it follows from membership of
    the project it belongs to, and nothing else.
    """

    # `table` is a reserved word in SQL. The stored name avoids it so that
    # anybody reading the database by hand does not have to quote it.
    __tablename__ = "projecttable"

    __table_args__ = (
        # A project names its own tables, and two projects may pick the same
        # name without colliding, because they are kept in separate
        # namespaces inside the datastore.
        UniqueConstraint("project_id", "name", name="uq_projecttable_project_id_name"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(
        index=True,
        description=(
            "What the project calls this table, and what its members write in "
            "their SQL."
        ),
    )
    project_id: UUID = Field(
        foreign_key="project.id",
        index=True,
        description="The project that governs this table.",
    )
    datastore_name: str = Field(
        foreign_key="datastore.name",
        index=True,
        description="The datastore holding the data.",
    )
    description: str | None = None
    creation_date: datetime = Field(default_factory=datetime.now)
