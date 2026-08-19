"""Give projects a second thing to hold: blobs.

Tables were the first project level object. This adds the second, for data
that has no shape the platform knows: a blob records that a project has
claimed a key inside one of the platform's datastores.

There is no table of containers or folders to go with it. A blob key may read
like a path, but the slashes are part of one name, so the only hierarchy is
the one a `LIKE 'prefix%'` finds.

Nothing here imports from `src`, for the same reason the baseline does not: a
revision has to keep describing what it did long after the models have moved
on.

Revision ID: 0005_project_blobs
Revises: 0004_api_keys
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_project_blobs"
down_revision: str | Sequence[str] | None = "0004_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the table of blobs.

    The stored name is `projectblob`, matching `projecttable` beside it, so
    that the two project level objects read alike to anybody looking at the
    database by hand.
    """
    op.create_table(
        "projectblob",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("datastore_name", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("creation_date", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["datastore_name"], ["datastore.name"]),
        sa.PrimaryKeyConstraint("id"),
        # A project names its own blobs; two projects may pick the same key,
        # because a datastore keeps each project's blobs apart.
        sa.UniqueConstraint("project_id", "key", name="uq_projectblob_project_id_key"),
    )
    op.create_index("ix_projectblob_key", "projectblob", ["key"])
    op.create_index("ix_projectblob_project_id", "projectblob", ["project_id"])
    op.create_index("ix_projectblob_datastore_name", "projectblob", ["datastore_name"])


def downgrade() -> None:
    """Forget every blob the platform had recorded.

    Only the platform's record goes. The data itself is inside the object
    stores, and this revision has no way to reach it, so downgrading leaves
    every blob behind under a key nothing now explains.
    """
    op.drop_index("ix_projectblob_datastore_name", table_name="projectblob")
    op.drop_index("ix_projectblob_project_id", table_name="projectblob")
    op.drop_index("ix_projectblob_key", table_name="projectblob")
    op.drop_table("projectblob")
