"""Bringing the database schema up to date.

The schema is described by the revisions under `migrations/`, and this module
is what applies them. Nothing else in the platform knows that Alembic exists:
callers ask for a database that matches the models, and get one.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from loguru import logger
from sqlalchemy import Connection, Engine

from src.platform.exceptions import SchemaMigrationError

__all__ = ["upgrade_to_head"]

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
            command.upgrade(_alembic_configuration(connection=connection), "head")
    except CommandError as error:
        raise SchemaMigrationError(
            f"The database could not be migrated: {error}"
        ) from error

    logger.info("Database schema is up to date")
