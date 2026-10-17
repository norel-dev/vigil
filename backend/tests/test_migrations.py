"""Tests of the migrations themselves.

The migrations must describe the same schema the models do, apply cleanly to
an empty database, and refuse a database they cannot account for.
"""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text
from sqlmodel import SQLModel

# Imported so that every table is declared on the metadata the comparison
# below runs against, exactly as migrations/env.py does it.
from src.database.engine import create_database_engine
from src.database.migrations import upgrade_to_head
from src.features.blobs import model as blobs_model  # noqa: F401
from src.features.datastores import model as datastores_model  # noqa: F401
from src.features.projects import model as projects_model  # noqa: F401
from src.features.tables import model as tables_model  # noqa: F401
from src.features.users import model as users_model  # noqa: F401
from src.identity import model as identity_model  # noqa: F401
from src.platform.config import DatabaseConfig
from src.platform.exceptions import SchemaMigrationError

#: Alembic's configuration, beside the application.
ALEMBIC_CONFIGURATION = Path(__file__).resolve().parent.parent / "alembic.ini"


def _engine_at(*, url: str) -> Engine:
    """Return an engine bound to the database at `url`.

    Args:
        url: The test's own empty database, from the `database_url` fixture.

    Returns:
        Engine: An engine for that database.
    """
    return create_database_engine(config=DatabaseConfig(url=url))


def test_the_migrations_produce_the_schema_the_models_describe(engine: Engine) -> None:
    """A model changed without a migration fails here rather than in production.

    The `engine` fixture has already migrated the database to head, so any
    difference the comparison finds is a revision somebody forgot to write.
    """
    with engine.connect() as connection:
        difference = compare_metadata(
            MigrationContext.configure(connection), SQLModel.metadata
        )

    assert difference == [], (
        "The models and the migrations disagree. Run "
        "`uv run alembic revision --autogenerate -m '<what changed>'`."
    )


def test_upgrading_an_up_to_date_database_changes_nothing(database_url: str) -> None:
    """The API migrates on every start, so doing it twice has to be harmless."""
    engine = _engine_at(url=database_url)

    upgrade_to_head(engine=engine)
    before = sorted(inspect(engine).get_table_names())
    upgrade_to_head(engine=engine)
    after = sorted(inspect(engine).get_table_names())

    assert before == after
    engine.dispose()


def test_a_fresh_database_ends_up_at_the_latest_revision(database_url: str) -> None:
    """A database built from nothing is stamped, so the next upgrade knows where it is."""
    engine = _engine_at(url=database_url)

    upgrade_to_head(engine=engine)

    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()

    head = ScriptDirectory.from_config(Config(str(ALEMBIC_CONFIGURATION))).get_current_head()
    assert revision == head
    engine.dispose()


@pytest.mark.parametrize(
    "table_name",
    ["user", "project", "projectmember", "datastore", "projecttable", "apikey"],
)
def test_every_table_the_models_declare_exists_after_migrating(
    engine: Engine, table_name: str
) -> None:
    """The tables the application reads and writes are all there.

    Args:
        engine: The migrated test database.
        table_name: Name of a table the models declare.
    """
    assert inspect(engine).has_table(table_name)


def test_a_database_stamped_with_an_unknown_revision_refuses_to_migrate(
    database_url: str,
) -> None:
    """A database from a newer build is reported rather than migrated blindly.

    The usual cause is a rollback: the database was upgraded by a version that
    has migrations this one has never heard of. There is no safe guess to make
    about a schema nothing here describes, so the process refuses to start
    instead of serving requests against it.
    """
    engine = _engine_at(url=database_url)
    upgrade_to_head(engine=engine)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = '9999_from_the_future'")
        )

    with pytest.raises(SchemaMigrationError, match="could not be migrated"):
        upgrade_to_head(engine=engine)

    engine.dispose()


def test_the_failure_says_the_database_could_not_be_migrated(database_url: str) -> None:
    """Alembic's own explanation is carried through, since it names the revision."""
    engine = _engine_at(url=database_url)
    upgrade_to_head(engine=engine)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = '9999_from_the_future'")
        )

    with pytest.raises(SchemaMigrationError, match="9999_from_the_future"):
        upgrade_to_head(engine=engine)

    engine.dispose()
