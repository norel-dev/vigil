"""Bringing the database schema up to date.

The schema is described by the revisions under `migrations/`, and this module
is what applies them. Nothing else in the platform knows that Alembic exists:
callers ask for a database that matches the models, and get one.

The one subtlety here is history. Databases created before this module
existed were built by `SQLModel.metadata.create_all` and carry no record of
which revision they are at, so Alembic would try to create tables that are
already there. Those databases are stamped with the baseline first, which
says "you are already at this revision" without touching a table, and are
then upgraded like any other.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from loguru import logger
from sqlalchemy import Connection, Engine, inspect

from src.platform.exceptions import SchemaMigrationError

__all__ = ["upgrade_to_head"]

#: The revision describing the schema as `create_all` used to produce it.
BASELINE_REVISION = "0001_baseline"

#: Tables that only a pre-Alembic database can have without an Alembic
#: version to go with them. Finding any of them is what identifies one.
_BASELINE_TABLES = frozenset({"user", "project", "projectmember", "datastore", "catalog"})

#: Alembic's configuration file, beside the application rather than beside
#: this module, so that the process can be started from any directory. It is
#: found by walking up out of `src`, so that moving this module within the
#: package cannot silently point it somewhere else.
_ALEMBIC_CONFIGURATION = (
    Path(__file__).resolve().parents[2] / "alembic.ini"
)


def _alembic_configuration(*, connection: Connection) -> Config:
    """Build an Alembic configuration bound to an open connection.

    Args:
        connection: The connection the migrations should run on.

    Returns:
        Config: A configuration that will migrate `connection`.
    """
    config = Config(str(_ALEMBIC_CONFIGURATION))
    config.attributes["connection"] = connection
    # The application has already configured its own logging, and Alembic's
    # ini file would replace it wholesale.
    config.attributes["configure_logger"] = False
    return config


def _predates_alembic(*, connection: Connection) -> bool:
    """Report whether the database was built before migrations were used.

    Args:
        connection: An open connection to the database.

    Returns:
        bool: True if the database holds platform tables but no revision.
    """
    tables = set(inspect(connection).get_table_names())
    return "alembic_version" not in tables and bool(_BASELINE_TABLES & tables)


def upgrade_to_head(*, engine: Engine) -> None:
    """Apply every migration the database behind `engine` is missing.

    Running this against a database that is already up to date does nothing,
    which is what makes it safe to call on every start.

    Args:
        engine: The engine whose database should be brought up to date.

    Raises:
        SchemaMigrationError: If the database could not be migrated. The
            process must not serve requests against a schema it cannot
            account for.
    """
    try:
        with engine.begin() as connection:
            config = _alembic_configuration(connection=connection)

            if _predates_alembic(connection=connection):
                logger.info(
                    "The database was created before migrations were used; "
                    "recording it as {} before upgrading",
                    BASELINE_REVISION,
                )
                command.stamp(config, BASELINE_REVISION)

            command.upgrade(config, "head")
    except CommandError as error:
        raise SchemaMigrationError(
            f"The database could not be migrated: {error}"
        ) from error

    logger.info("Database schema is up to date")
