"""A datastore backed by SQLite database files on the API's own disk."""

import sqlite3
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import Field as PydanticField

from src.features.datastores.implementations._sqlite_privileges import (
    Authorizer,
    build_authorizer,
    is_refusal,
)
from src.features.datastores.implementations.base import DataStoreImplementationBase
from src.features.datastores.storage import DataStoreQuery, DataStoreQueryResponse, DataType
from src.features.tables.storage import (
    ColumnDefinition,
    QueryPrivilege,
    primary_key_of,
    validate_identifier,
)
from src.platform.exceptions import (
    QueryFailedError,
    QueryRefusedError,
    TableProvisioningError,
)

__all__ = ["SQLiteDataStore"]


class SQLiteDataStore(DataStoreImplementationBase):
    """A SQLite datastore, connected via a path/URI to the database file.

    This implementation also holds tables, and so satisfies the `TableStorage`
    protocol. SQLite has no users to grant rights to, so the two privilege
    levels the platform relies on are realised differently here: provisioning
    opens an ordinary connection, while a caller's query opens one carrying an
    authorization callback that confines it to a single table. The rules of
    that callback live in `src.features.datastores.implementations._sqlite_privileges`.

    SQLite has no schemas either, so a namespace becomes a database file of
    its own, sitting beside the configured one and named after it. That is
    what lets each project call its tables whatever it likes: two projects
    asking for `customers` end up in two different files, and neither
    statement has to be rewritten for them not to collide.
    """

    implementation: Literal["sqlite"] = "sqlite"
    sqlite_connection_string: str = PydanticField(
        description=(
            "Path to the SQLite database file. Each project's tables are kept "
            "in a file of their own beside it, named after this one."
        ),
        examples=["/data/mydb.db"],
    )

    async def get_data_type(self) -> DataType:
        return DataType.TABLE

    def _database_for(self, *, namespace: str) -> str:
        """Return the path of the database file holding `namespace`.

        Args:
            namespace: The namespace whose database is wanted.

        Returns:
            str: Path to that namespace's SQLite file.

        Raises:
            TableProvisioningError: If the namespace is not a plain name, and
                so could point the path somewhere it does not belong.
        """
        try:
            validate_identifier(name=namespace, kind="namespace")
        except ValueError as error:
            raise TableProvisioningError(str(error)) from error

        configured = Path(self.sqlite_connection_string)
        return str(configured.with_name(f"{configured.stem}__{namespace}{configured.suffix}"))

    @contextmanager
    def _connect(
        self, *, database: str | None = None, authorizer: Authorizer | None = None
    ) -> Iterator[sqlite3.Connection]:
        """Open a connection, commit if the body succeeds, and always close.

        Args:
            database: The file to open, defaulting to the configured one.
            authorizer: The privilege callback to install, or None for an
                unrestricted connection. Only provisioning passes None.

        Yields:
            sqlite3.Connection: The open connection.
        """
        connection = sqlite3.connect(database or self.sqlite_connection_string)
        if authorizer is not None:
            connection.set_authorizer(authorizer)

        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    async def query(self, query: DataStoreQuery) -> DataStoreQueryResponse:
        """Query method for SQLite.

        This is simply sqlite compatible SQL, run without restriction against
        the configured database. Only platform administrators reach this,
        because only they may act on a datastore itself.

        Note that projects' tables are not here: each project's tables live in
        a database of their own beside this one, so this sees the datastore's
        own database and nothing a project has created. A project's access to
        its own table goes through `query_table`.
        """
        query_start_time = time.time()
        with self._connect() as connection:
            return DataStoreQueryResponse(
                data=connection.execute(query.query).fetchall(),
                metadata={},
                latency=time.time() - query_start_time,
            )

    async def create_table(
        self, *, namespace: str, name: str, columns: Sequence[ColumnDefinition]
    ) -> None:
        """Create the table `name`, using the privilege a caller never gets.

        Args:
            namespace: The project whose database the table belongs in.
            name: Name of the table to create.
            columns: The columns it should have, in order.

        Raises:
            TableProvisioningError: If the table could not be created.
            ValueError: If the columns do not describe a usable primary key.
        """
        validate_identifier(name=name, kind="table name")
        if not columns:
            raise TableProvisioningError(
                f"The table '{name}' was asked for with no columns, and a table "
                "must have at least one."
            )

        key = primary_key_of(columns=columns)

        definitions = ", ".join(
            f"{column.name} {column.type}" + ("" if column.nullable else " NOT NULL")
            for column in columns
        )
        if key:
            # A key of one column is written the same way as a key of several,
            # because SQLite reads the two forms alike: a lone INTEGER column
            # named in this clause still becomes an alias for the rowid, just
            # as it would had PRIMARY KEY been written against the column
            # itself. One form for both keeps this from having two cases.
            definitions += f", PRIMARY KEY ({', '.join(key)})"

        try:
            with self._connect(database=self._database_for(namespace=namespace)) as connection:
                connection.execute(f"CREATE TABLE {name} ({definitions})")
        except sqlite3.DatabaseError as error:
            raise TableProvisioningError(
                f"The table '{name}' could not be created: {error}"
            ) from error

    async def drop_table(self, *, namespace: str, name: str) -> None:
        """Destroy the table `name` and everything in it.

        Args:
            namespace: The project whose database the table belongs in.
            name: Name of the table to destroy.

        Raises:
            TableProvisioningError: If the table could not be dropped.
        """
        validate_identifier(name=name, kind="table name")

        try:
            with self._connect(database=self._database_for(namespace=namespace)) as connection:
                connection.execute(f"DROP TABLE IF EXISTS {name}")
        except sqlite3.DatabaseError as error:
            raise TableProvisioningError(
                f"The table '{name}' could not be dropped: {error}"
            ) from error

    async def query_table(
        self,
        *,
        namespace: str,
        name: str,
        query: DataStoreQuery,
        privilege: QueryPrivilege,
    ) -> DataStoreQueryResponse:
        """Run `query` against `name` on a connection that can do no more.

        The statement is never inspected. It is handed to SQLite on a
        connection opened against this namespace's own database file, and
        carrying an authorization callback that refuses, while compiling, any
        step reaching beyond `name` or beyond `privilege`. The two together
        are why a caller may write their own table's name: the file keeps
        other projects out of reach, and the callback keeps them to one table
        within it.

        Args:
            namespace: The project whose database the table belongs in.
            name: Name of the only table the query may touch.
            query: The statement to run.
            privilege: The most the statement is allowed to do.

        Returns:
            DataStoreQueryResponse: The rows, the column names, and how long
                the statement took.

        Raises:
            QueryRefusedError: If SQLite refused the statement.
            QueryFailedError: If the statement was allowed but did not run.
        """
        validate_identifier(name=name, kind="table name")
        authorizer = build_authorizer(table=name, privilege=privilege)
        database = self._database_for(namespace=namespace)
        query_start_time = time.time()

        try:
            with self._connect(database=database, authorizer=authorizer) as connection:
                cursor = connection.execute(query.query)
                rows = cursor.fetchall()
                columns = [column[0] for column in cursor.description or ()]
        except sqlite3.DatabaseError as error:
            if is_refusal(error=error):
                raise QueryRefusedError(
                    f"The statement was refused: {error}. A table may only be "
                    "read and written through the table it belongs to, and "
                    "never created or dropped."
                ) from error

            # Everything else is the caller's statement not working: a syntax
            # error, an unknown column, or - since `execute` takes one
            # statement only - an attempt to hide a second statement behind a
            # harmless first, which arrives here as a ProgrammingError.
            raise QueryFailedError(f"The statement could not be run: {error}") from error

        return DataStoreQueryResponse(
            data=rows,
            metadata={"columns": columns},
            latency=time.time() - query_start_time,
        )
