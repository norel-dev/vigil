"""Let a datastore be registered without being offered.

Until now every datastore the platform knew about was a datastore every user
could find, because the catalogue answered with all of them. This adds the
column that separates the two: a public datastore is on the list, a private
one is only in the database.

The column is not nullable and every datastore that already exists becomes
public, which is what they all effectively were. Nothing about who may reach
a datastore changes here, and no other table is touched.

Nothing here imports from `src`, for the same reason the baseline does not: a
revision has to keep describing what it did long after the models have moved
on.

Revision ID: 0006_datastore_visibility
Revises: 0005_project_blobs
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_datastore_visibility"
down_revision: str | Sequence[str] | None = "0005_project_blobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The column as the model declares it. Named so that the batch rebuild below
#: and the index beside it are describing the same thing.
VISIBILITY = sa.Enum("PUBLIC", "PRIVATE", name="datastorevisibility")


def upgrade() -> None:
    """Add the visibility column, with every existing datastore public.

    The column arrives nullable so that the rows already in the table have
    somewhere to put their answer, is filled in, and only then becomes
    required. A default is deliberately not left on the column: what a new
    datastore gets when nobody says is a decision the API makes, and a
    database that answers it too would be a second place to change it.
    """
    with op.batch_alter_table("datastore", schema=None) as batch_op:
        batch_op.add_column(sa.Column("visibility", VISIBILITY, nullable=True))

    op.execute("UPDATE datastore SET visibility = 'PUBLIC' WHERE visibility IS NULL")

    with op.batch_alter_table("datastore", schema=None) as batch_op:
        batch_op.alter_column("visibility", existing_type=VISIBILITY, nullable=False)

    op.create_index("ix_datastore_visibility", "datastore", ["visibility"])


def downgrade() -> None:
    """Forget which datastores were private.

    Every datastore goes back to being on the list, including the ones an
    administrator had registered for themselves. That is not recoverable by
    upgrading again: this revision is what threw the answer away.
    """
    op.drop_index("ix_datastore_visibility", table_name="datastore")

    with op.batch_alter_table("datastore", schema=None) as batch_op:
        batch_op.drop_column("visibility")

    VISIBILITY.drop(op.get_bind(), checkfirst=True)
