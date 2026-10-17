"""How Alembic reaches the database and what it compares against.

This runs both ways round. From the command line it loads the platform's own
configuration, so `alembic upgrade head` migrates whichever database the API
is configured to use, and there is no second copy of the URL to keep in step.
Driven from inside the process, it is handed a connection through
`config.attributes` and uses that instead, which is what lets the API bring
its database up to date as it starts and what lets the tests migrate a
throwaway database.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool
from sqlmodel import SQLModel

# Imported for the side effect of declaring their tables on SQLModel's
# metadata: a model that is never imported is a model autogenerate cannot see,
# and a table nobody would ever get a migration for. Every feature holding a
# model belongs on this list, so adding one means adding a line here.
from src.features.blobs import model as blobs_model  # noqa: F401
from src.features.datastores import model as datastores_model  # noqa: F401
from src.features.projects import model as projects_model  # noqa: F401
from src.features.tables import model as tables_model  # noqa: F401
from src.features.users import model as users_model  # noqa: F401
from src.identity import model as identity_model  # noqa: F401
from src.platform.environment import load_configuration

#: Alembic's own configuration, from alembic.ini plus anything the caller
#: attached before invoking us.
config = context.config

# Configuring logging from the ini file is right for the command line and
# wrong from inside a running API, which has already set its logging up. The
# caller says which of the two this is.
if config.attributes.get("configure_logger", True) and config.config_file_name is not None:
    fileConfig(config.config_file_name)

#: What the schema is compared against when autogenerating a revision.
target_metadata = SQLModel.metadata


def _database_url() -> str:
    """Return the database URL from the platform configuration.

    Returns:
        str: The SQLAlchemy URL of the metadata database.

    Raises:
        ConfigurationError: If the configuration could not be loaded.
    """
    return load_configuration().database.url


def _run(*, connection: Connection) -> None:
    """Run every pending migration against `connection`.

    Args:
        connection: An open connection to the database being migrated.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Emit the migrations as SQL, without connecting to anything."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run the migrations against a live database.

    The connection is the caller's if they supplied one, so that a migration
    driven from the API takes part in whatever transaction that process is
    already in rather than opening a second one behind its back.
    """
    if isinstance(borrowed := config.attributes.get("connection"), Connection):
        _run(connection=borrowed)
        return

    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as opened:
            _run(connection=opened)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
