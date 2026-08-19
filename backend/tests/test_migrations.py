"""Tests of the migrations themselves.

Two things have to stay true for a database to stop breaking: the migrations
must describe the same schema the models do, and a database that was created
before the migrations existed must be carried forward rather than left in a
state nothing can read.
"""

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect, text
from sqlmodel import SQLModel

# Imported so that every table is declared on the metadata the comparison
# below runs against, exactly as migrations/env.py does it.
from src.database.engine import create_database_engine
from src.database.migrations import BASELINE_REVISION, upgrade_to_head
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


def _engine_at(*, path: Path) -> Engine:
    """Return an engine bound to a SQLite file at `path`.

    Args:
        path: Where the database file should live.

    Returns:
        Engine: An engine for that file.
    """
    return create_database_engine(config=DatabaseConfig(url=f"sqlite:///{path}"))


def _build_a_pre_alembic_database(*, engine: Engine) -> None:
    """Leave `engine`'s database in the state the old code used to leave it.

    The old code called `SQLModel.metadata.create_all`, which produced the
    schema the baseline revision describes and recorded nothing about it.
    That is reproduced here by migrating to the baseline and then forgetting
    that it happened.

    Args:
        engine: The engine whose database should be taken back in time.
    """
    with engine.begin() as connection:
        config = Config(str(ALEMBIC_CONFIGURATION))
        config.attributes["connection"] = connection
        config.attributes["configure_logger"] = False
        command.upgrade(config, BASELINE_REVISION)
        connection.execute(text("DROP TABLE alembic_version"))


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


def test_a_database_from_before_alembic_is_carried_forward(tmp_path: Path) -> None:
    """The databases that exist today are upgraded, not rejected.

    This is the case that used to break: a database created by the old code
    has the columns the permission model change removed, and nothing to say
    which revision it is at.
    """
    engine = _engine_at(path=tmp_path / "old.db")
    _build_a_pre_alembic_database(engine=engine)

    upgrade_to_head(engine=engine)

    inspector = inspect(engine)
    datastore_columns = {column["name"] for column in inspector.get_columns("datastore")}
    assert "project_id" not in datastore_columns
    assert "owner_id" not in datastore_columns
    assert "catalog" not in inspector.get_table_names()
    engine.dispose()


def test_upgrading_a_pre_alembic_database_keeps_its_rows(tmp_path: Path) -> None:
    """Migrating is not a euphemism for starting again.

    A datastore registered under the old model loses the project and the
    owner it used to carry, because those are what the change removed, but
    the datastore itself and the connection details behind it survive.
    """
    engine = _engine_at(path=tmp_path / "old.db")
    _build_a_pre_alembic_database(engine=engine)
    implementation = {"implementation": "sqlite", "sqlite_connection_string": "/data/a.db"}

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO datastore "
                "(name, implementation, description, project_id, owner_id, creation_date) "
                "VALUES (:name, :implementation, :description, :project, :owner, :created)"
            ),
            {
                "name": "warehouse",
                "implementation": json.dumps(implementation),
                "description": "the old warehouse",
                "project": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "owner": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "created": "2026-01-01 00:00:00",
            },
        )

    upgrade_to_head(engine=engine)

    with engine.connect() as connection:
        stored = connection.execute(
            text("SELECT name, implementation, description FROM datastore")
        ).all()

    assert stored == [("warehouse", json.dumps(implementation), "the old warehouse")]
    engine.dispose()


def test_upgrading_an_up_to_date_database_changes_nothing(tmp_path: Path) -> None:
    """The API migrates on every start, so doing it twice has to be harmless."""
    engine = _engine_at(path=tmp_path / "fresh.db")

    upgrade_to_head(engine=engine)
    before = sorted(inspect(engine).get_table_names())
    upgrade_to_head(engine=engine)
    after = sorted(inspect(engine).get_table_names())

    assert before == after
    engine.dispose()


def test_a_fresh_database_ends_up_at_the_latest_revision(tmp_path: Path) -> None:
    """A database built from nothing is stamped, so the next upgrade knows where it is."""
    engine = _engine_at(path=tmp_path / "fresh.db")

    upgrade_to_head(engine=engine)

    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()

    assert revision is not None
    assert revision != BASELINE_REVISION, "the baseline is not the latest revision"
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
    tmp_path: Path,
) -> None:
    """A database from a newer build is reported rather than migrated blindly.

    The usual cause is a rollback: the database was upgraded by a version that
    has migrations this one has never heard of. There is no safe guess to make
    about a schema nothing here describes, so the process refuses to start
    instead of serving requests against it.
    """
    engine = _engine_at(path=tmp_path / "from-the-future.db")
    upgrade_to_head(engine=engine)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = '9999_from_the_future'")
        )

    with pytest.raises(SchemaMigrationError, match="could not be migrated"):
        upgrade_to_head(engine=engine)

    engine.dispose()


def test_the_failure_says_the_database_could_not_be_migrated(tmp_path: Path) -> None:
    """Alembic's own explanation is carried through, since it names the revision."""
    engine = _engine_at(path=tmp_path / "from-the-future.db")
    upgrade_to_head(engine=engine)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = '9999_from_the_future'")
        )

    with pytest.raises(SchemaMigrationError, match="9999_from_the_future"):
        upgrade_to_head(engine=engine)

    engine.dispose()
