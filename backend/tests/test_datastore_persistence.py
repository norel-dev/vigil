"""Tests of how a datastore's implementation is stored and read back.

An implementation is one of several shapes - SQLite, MinIO - and it is kept in
a single JSON column, so the column type is what turns it back into the
concrete thing the platform can use. Everything else assumes that has already
happened: the service layer asks an implementation what it holds and calls
methods on it, and would get a plain dictionary if this were wrong.

The secret is the delicate part. It has to be written in the clear, because a
platform that cannot reconnect to its own storage after a restart is no use,
and it has to be masked absolutely everywhere else. The default is therefore
to mask, and this one destination is the exception - which is the way round
that fails safe.
"""


from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect
from sqlmodel import Session, select

from src.features.datastores.implementations import MinIODataStore, SQLiteDataStore
from src.features.datastores.model import (
    DataStore,
    DataStoreImplementationColumn,
    DataStoreVisibility,
)

#: The secret the round trip tests write and expect to get back.
SECRET = "the-platforms-own-minio-secret"


def _store_named(*, name: str, secret: str = SECRET) -> DataStore:
    """Return an unsaved MinIO datastore called `name`.

    Args:
        name: What to register it as.
        secret: The secret key it holds.

    Returns:
        DataStore: A datastore ready to be added to a session.
    """
    return DataStore(
        name=name,
        description=None,
        implementation=MinIODataStore(
            endpoint="minio.example.com:9000",
            access_key="an-access-key",
            secret_key=SecretStr(secret),
            secure=False,
        ),
    )


# --- reading an implementation back as itself -------------------------------


def test_an_implementation_is_read_back_as_the_type_it_was_stored_as(
    engine: Engine,
) -> None:
    """Not as the dictionary the column holds, which nothing could act through."""
    with Session(engine) as session:
        session.add(_store_named(name="objects"))
        session.commit()

    with Session(engine) as session:
        stored = session.exec(select(DataStore).where(DataStore.name == "objects")).one()

    assert isinstance(stored.implementation, MinIODataStore)
    assert stored.implementation.endpoint == "minio.example.com:9000"


def test_each_kind_of_implementation_comes_back_as_its_own_kind(
    engine: Engine,
) -> None:
    """One column holds several shapes, so the shape has to survive the trip."""
    with Session(engine) as session:
        session.add(_store_named(name="objects"))
        session.add(
            DataStore(
                name="warehouse",
                description=None,
                implementation=SQLiteDataStore(sqlite_connection_string="/tmp/w.db"),
            )
        )
        session.commit()

    with Session(engine) as session:
        by_name = {
            store.name: store.implementation
            for store in session.exec(select(DataStore)).all()
        }

    assert isinstance(by_name["objects"], MinIODataStore)
    assert isinstance(by_name["warehouse"], SQLiteDataStore)


def test_a_datastore_keeps_the_visibility_it_was_given(engine: Engine) -> None:
    """Which is what the catalogue is built from, so it has to persist."""
    store = _store_named(name="private")
    store.visibility = DataStoreVisibility.PRIVATE

    with Session(engine) as session:
        session.add(store)
        session.commit()

    with Session(engine) as session:
        read_back = session.exec(
            select(DataStore).where(DataStore.name == "private")
        ).one()

    assert read_back.visibility is DataStoreVisibility.PRIVATE


# --- the secret -------------------------------------------------------------


def test_the_secret_survives_the_round_trip_so_the_platform_can_reconnect(
    engine: Engine,
) -> None:
    """The one place the secret is written in the clear, and it has to be.

    A masked secret would be stored happily and would fail at the first
    request after a restart, which is the worst moment to find out.
    """
    with Session(engine) as session:
        session.add(_store_named(name="objects"))
        session.commit()

    with Session(engine) as session:
        stored = session.exec(select(DataStore).where(DataStore.name == "objects")).one()

    assert isinstance(stored.implementation, MinIODataStore)
    assert stored.implementation.secret_key.get_secret_value() == SECRET


def test_the_secret_is_still_wrapped_after_being_read_back(engine: Engine) -> None:
    """It comes back a `SecretStr`, so it keeps its own guards from then on."""
    with Session(engine) as session:
        session.add(_store_named(name="objects"))
        session.commit()

    with Session(engine) as session:
        stored = session.exec(select(DataStore).where(DataStore.name == "objects")).one()

    assert isinstance(stored.implementation, MinIODataStore)
    assert SECRET not in repr(stored.implementation)
    assert SECRET not in str(stored.implementation)


def test_dumping_an_implementation_without_asking_masks_the_secret() -> None:
    """The default is the safe one: revealing takes saying so, explicitly."""
    implementation = MinIODataStore(
        endpoint="minio.example.com:9000",
        access_key="an-access-key",
        secret_key=SecretStr(SECRET),
        secure=False,
    )

    assert SECRET not in str(implementation.model_dump(mode="json"))


# --- the empty column -------------------------------------------------------


def test_nothing_is_written_as_nothing() -> None:
    """A column type has to answer for `None`, whatever the model allows.

    Nothing on the platform stores a datastore without an implementation.
    What this pins down is that the column does not try to serialize the
    absence of one, which is how a `None` slipping through turns into a
    confusing failure rather than a `None`.
    """
    column = DataStoreImplementationColumn()

    assert column.process_bind_param(None, dialect=postgresql_dialect()) is None


def test_nothing_is_read_back_as_nothing() -> None:
    """The same, in the direction that would otherwise try to parse a null."""
    column = DataStoreImplementationColumn()

    assert column.process_result_value(None, dialect=postgresql_dialect()) is None
