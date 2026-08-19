"""Move datastores out of the project hierarchy.

Datastores describe the storage the whole platform is built on, so they stop
belonging to a project and stop recording a creator. Catalogs go with them:
nothing sits under a project yet, and the table was never written to.

Revision ID: 0002_system_level_datastores
Revises: 0001_baseline
Create Date: 2026-08-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_system_level_datastores"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: SQLite names none of its constraints, and rebuilding a table in batch mode
#: means recreating them by name. This tells Alembic what to call the ones it
#: finds, so the rebuild below does not fail on an unnamed foreign key.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def upgrade() -> None:
    """Detach datastores from projects, and forget catalogs."""
    op.drop_index("ix_catalog_project_id", table_name="catalog")
    op.drop_table("catalog")

    op.drop_index("ix_datastore_owner_id", table_name="datastore")
    op.drop_index("ix_datastore_project_id", table_name="datastore")
    with op.batch_alter_table(
        "datastore", schema=None, naming_convention=NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_column("owner_id")
        batch_op.drop_column("project_id")


def downgrade() -> None:
    """Put the columns and the catalog table back.

    The project and the owner a datastore used to have cannot be recovered:
    this revision is what threw them away. The columns therefore come back
    nullable and empty, and any datastore that predates the downgrade will
    have to be assigned a project by hand.
    """
    with op.batch_alter_table(
        "datastore", schema=None, naming_convention=NAMING_CONVENTION
    ) as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("owner_id", sa.Uuid(), nullable=True))

    op.create_index("ix_datastore_project_id", "datastore", ["project_id"])
    op.create_index("ix_datastore_owner_id", "datastore", ["owner_id"])

    op.create_table(
        "catalog",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catalog_project_id", "catalog", ["project_id"])
