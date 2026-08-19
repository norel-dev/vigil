"""Give projects something to hold: tables.

Datastores became system level in the previous revision, which left projects
with nothing underneath them. This adds the first project level object: a
table, which records that a project has claimed a named table inside one of
the platform's datastores.

Nothing here imports from `src`, for the same reason the baseline does not: a
revision has to keep describing what it did long after the models have moved
on.

Revision ID: 0003_project_tables
Revises: 0002_system_level_datastores
Create Date: 2026-08-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_project_tables"
down_revision: str | Sequence[str] | None = "0002_system_level_datastores"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the table of tables.

    The stored name is `projecttable` rather than `table`, which is a reserved
    word every reader would otherwise have to quote by hand.
    """
    op.create_table(
        "projecttable",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("datastore_name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("creation_date", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["datastore_name"], ["datastore.name"]),
        sa.PrimaryKeyConstraint("id"),
        # A project names its own tables; two projects may pick the same name,
        # because a datastore keeps each project's tables apart.
        sa.UniqueConstraint("project_id", "name", name="uq_projecttable_project_id_name"),
    )
    op.create_index("ix_projecttable_name", "projecttable", ["name"])
    op.create_index("ix_projecttable_project_id", "projecttable", ["project_id"])
    op.create_index("ix_projecttable_datastore_name", "projecttable", ["datastore_name"])


def downgrade() -> None:
    """Forget every table the platform had recorded.

    Only the platform's record goes. The tables themselves are inside the
    datastores, and this revision has no way to reach them, so downgrading
    leaves them behind with the generated names nothing now explains.
    """
    op.drop_index("ix_projecttable_datastore_name", table_name="projecttable")
    op.drop_index("ix_projecttable_project_id", table_name="projecttable")
    op.drop_index("ix_projecttable_name", table_name="projecttable")
    op.drop_table("projecttable")
