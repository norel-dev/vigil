"""Connections to the metadata database.

This module owns the SQLAlchemy engine and hands out sessions. Everything
above it works with a `Session` and never learns which database is behind it.
What shape that database is in is `src.database.migrations`'s business, not this module's.
"""

from collections.abc import Iterator

from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from src.platform.config import DatabaseConfig

__all__ = ["create_database_engine", "open_session"]


def create_database_engine(*, config: DatabaseConfig) -> Engine:
    """Create the engine described by `config`.

    Args:
        config: The database section of the application configuration.

    Returns:
        Engine: A SQLAlchemy engine pointing at the metadata database.
    """
    return create_engine(config.url, echo=config.echo)


def open_session(*, engine: Engine) -> Iterator[Session]:
    """Yield a session bound to `engine`, closing it when the caller is done.

    Args:
        engine: The engine to bind the session to.

    Yields:
        Session: A session that is closed once the caller finishes with it.
    """
    with Session(engine) as session:
        yield session
