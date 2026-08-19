"""Replace Google accounts with API keys the platform issues itself.

Users used to be Google accounts, recognised by the `sub` claim Google put on
a token. They are now records the platform owns outright, and a caller proves
who they are with a key this platform generated. That makes `google_subject`
meaningless, and adds the table of keys.

Nothing here imports from `src`: a revision has to keep describing what it did
long after the models have moved on.

Revision ID: 0004_api_keys
Revises: 0003_project_tables
Create Date: 2026-08-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_api_keys"
down_revision: str | Sequence[str] | None = "0003_project_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the table of keys and drop the Google account column.

    The users themselves survive: their addresses, names and administrator
    flags are all still meaningful, and so is everything held against their
    ids. What they lose is the Google account they used to be reached
    through, which leaves every existing user without a way to authenticate
    until a key is issued to them. The administrators named in the
    configuration get theirs on the next start; the rest are given one
    through `POST /users/{id}/api-keys`.
    """
    op.create_table(
        "apikey",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("secret_hash", sa.String(), nullable=False),
        sa.Column("creation_date", sa.DateTime(), nullable=False),
        sa.Column("expiration_date", sa.DateTime(), nullable=True),
        sa.Column("revocation_date", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_apikey_user_id", "apikey", ["user_id"])
    # Unique, because the digest is what a presented key is looked up by: two
    # rows sharing one would make the caller behind it ambiguous.
    op.create_index("ix_apikey_secret_hash", "apikey", ["secret_hash"], unique=True)

    op.drop_index("ix_user_google_subject", table_name="user")
    with op.batch_alter_table("user") as batch:
        batch.drop_column("google_subject")


def downgrade() -> None:
    """Put the Google account column back, with nothing to fill it.

    The subjects it used to hold came from Google and were never ours to
    reconstruct, so each user is given a placeholder that satisfies the
    uniqueness the column carried. A downgraded database therefore has users
    that no Google sign in will match, and they have to be reconnected by
    hand.
    """
    with op.batch_alter_table("user") as batch:
        batch.add_column(sa.Column("google_subject", sa.String(), nullable=True))

    op.execute("UPDATE user SET google_subject = 'unlinked:' || id")

    with op.batch_alter_table("user") as batch:
        batch.alter_column("google_subject", nullable=False)

    op.create_index("ix_user_google_subject", "user", ["google_subject"], unique=True)

    op.drop_index("ix_apikey_secret_hash", table_name="apikey")
    op.drop_index("ix_apikey_user_id", table_name="apikey")
    op.drop_table("apikey")
