"""Blobs: what a project holds when the data has no shape the platform knows.

A blob is the platform's record of one object living inside some datastore.
Like a table, it is deliberately thin: how large the data is, when it last
changed and what its checksum is are the store's to know, and are asked of
the store rather than mirrored here. A caller uploads through a signed URL
that the platform never sees used, so any copy of those facts kept here would
be wrong within seconds of being written.

Blobs have no hierarchy. A key may read like a path - `reports/2026/q1.csv` -
but there is no folder in it and nothing to create before using it: that is
one blob with one name, and the slashes matter only to whoever reads the name
and to listing by prefix. This is why a project holds blobs directly rather
than holding containers that hold blobs.

There is one name, and it is the one the project chose. Each project's blobs
sit in a namespace of their own inside the datastore, so a key only has to be
unique within its project, and two projects may both hold `model.pkl`.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, UniqueConstraint

__all__ = ["Blob"]


class Blob(SQLModel, table=True):
    """An unstructured object belonging to a project, held by a datastore.

    A blob has no owner column for the same reason a project and a table have
    none: it sits at the project level, so who may touch it follows from
    membership of the project it belongs to, and nothing else.

    A blob's record can exist before its bytes do. Creating one records the
    blob and hands back a URL to upload through, and until somebody uses that
    URL the store holds nothing under the key. That is a normal state, not a
    broken one, and reading a blob reports it plainly.
    """

    __tablename__ = "projectblob"

    __table_args__ = (
        # A project names its own blobs, and two projects may pick the same
        # key without colliding, because they are kept in separate namespaces
        # inside the datastore.
        UniqueConstraint("project_id", "key", name="uq_projectblob_project_id_key"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    key: str = Field(
        index=True,
        description=(
            "What the project calls this blob. Slashes in it are part of the "
            "name, not folders, and are what listing by prefix goes on."
        ),
    )
    project_id: UUID = Field(
        foreign_key="project.id",
        index=True,
        description="The project that governs this blob.",
    )
    datastore_name: str = Field(
        foreign_key="datastore.name",
        index=True,
        description="The datastore holding the data.",
    )
    content_type: str | None = Field(
        default=None,
        description=(
            "The media type the project says this blob holds. It is recorded "
            "as told: the platform never sees the bytes to check it."
        ),
    )
    description: str | None = None
    creation_date: datetime = Field(default_factory=datetime.now)
