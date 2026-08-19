"""The schema as it stood before migrations existed.

This revision is a photograph, not a design: it describes the tables that
`SQLModel.metadata.create_all` used to produce, so that the databases created
that way can be stamped with it and then carried forward like any other.

A revision must keep working long after the models it was written beside have
changed, so nothing here imports from `src`. The types are the plain
SQLAlchemy ones the models happened to compile to at the time.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the pre-migration schema."""
    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("google_subject", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False),
        sa.Column("creation_date", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_email", "user", ["email"], unique=True)
    op.create_index("ix_user_google_subject", "user", ["google_subject"], unique=True)

    op.create_table(
        "project",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("creation_date", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_name", "project", ["name"], unique=True)

    op.create_table(
        "projectmember",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("VIEWER", "EDITOR", "ADMIN", "OWNER", name="projectrole"),
            nullable=False,
        ),
        sa.Column("creation_date", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
    )

    op.create_table(
        "catalog",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catalog_project_id", "catalog", ["project_id"])

    op.create_table(
        "datastore",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("implementation", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("creation_date", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_index("ix_datastore_project_id", "datastore", ["project_id"])
    op.create_index("ix_datastore_owner_id", "datastore", ["owner_id"])


def downgrade() -> None:
    """Drop everything this revision created."""
    op.drop_index("ix_datastore_owner_id", table_name="datastore")
    op.drop_index("ix_datastore_project_id", table_name="datastore")
    op.drop_table("datastore")

    op.drop_index("ix_catalog_project_id", table_name="catalog")
    op.drop_table("catalog")

    op.drop_table("projectmember")
    sa.Enum(name="projectrole").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_project_name", table_name="project")
    op.drop_table("project")

    op.drop_index("ix_user_google_subject", table_name="user")
    op.drop_index("ix_user_email", table_name="user")
    op.drop_table("user")
