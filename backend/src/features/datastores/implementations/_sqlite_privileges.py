"""The privilege rules of a restricted SQLite connection.

SQLite has no users to grant rights to, so the equivalent of connecting as a
restricted user is installing an authorization callback: SQLite consults it
while *compiling* each statement and refuses the statement outright if the
callback says no. That makes this a privilege boundary enforced by the engine
rather than a filter over statement text, which matters, because a filter has
to be right about every way of writing a query and this does not have to read
the query at all.

The rules below say the same thing twice over: a restricted connection may
touch exactly one table, and may never create or destroy anything. Everything
this module does not recognise is refused, so a SQLite version that grows a
new action code starts out forbidden rather than allowed.

Two details here were established by experiment rather than by reading, and
both are easy to get wrong:

- `SQLITE_ALTER_TABLE` passes its arguments the other way round from every
  other code: the database name arrives first and the table name second.
  Reading the table out of the first argument silently permits altering any
  table at all.
- Altering a table makes SQLite read `sqlite_master` on the caller's behalf,
  so refusing those reads breaks `ALTER` itself. Read/write connections are
  therefore able to read the schema, which is why the leak that remains is a
  leak of table definitions and never of anybody's rows.
"""

import sqlite3
from collections.abc import Callable

from src.features.tables.storage import QueryPrivilege

__all__ = ["Authorizer", "build_authorizer", "is_refusal"]

#: The shape SQLite expects of an authorization callback: an action code, two
#: action dependent arguments, the database name, and the trigger or view the
#: access came from.
type Authorizer = Callable[[int, str | None, str | None, str | None, str | None], int]

#: SQLite's own catalogue. Reading it is what `ALTER TABLE` needs, and writing
#: it is how a caller would rewrite the schema behind the platform's back.
_SCHEMA_TABLE = "sqlite_master"

#: Actions whose *first* argument names the table being acted on.
_READ_ACTIONS = frozenset({sqlite3.SQLITE_READ})
_WRITE_ACTIONS = frozenset(
    {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}
)

#: The actions SQLite performs against its own catalogue while carrying out an
#: `ALTER TABLE` on the caller's behalf.
_CATALOGUE_ACTIONS = _READ_ACTIONS | _WRITE_ACTIONS

#: Actions that say nothing about which object is being reached, and so cannot
#: on their own let a statement out of its table. Denying these would refuse
#: ordinary queries without making anything safer.
_MECHANICS = frozenset(
    {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_SAVEPOINT,
        sqlite3.SQLITE_RECURSIVE,
    }
)



def build_authorizer(*, table: str, privilege: QueryPrivilege) -> Authorizer:
    """Build a callback that confines statements to `table` at `privilege`.

    Args:
        table: Physical name of the only table statements may touch.
        privilege: The most a statement is allowed to do.

    Returns:
        Authorizer: A callback to install with `Connection.set_authorizer`.
    """
    may_write = privilege is QueryPrivilege.READ_WRITE

    def authorize(
        action: int,
        first: str | None,
        second: str | None,
        _database: str | None,
        _source: str | None,
    ) -> int:
        """Decide whether SQLite may compile one step of a statement.

        Args:
            action: The action code SQLite is asking about.
            first: The action's first argument, usually the table name.
            second: The action's second argument.
            _database: The database the action applies to.
            _source: The trigger or view the access came from.

        Returns:
            int: `sqlite3.SQLITE_OK` to permit the step, `SQLITE_DENY` to
                refuse the whole statement.
        """
        if action in _MECHANICS:
            return sqlite3.SQLITE_OK

        # Altering a table is spelled, internally, as reading and writing the
        # catalogue, so a connection that may alter has to be allowed both.
        # Permitting the writes gives nothing away: SQLite refuses to modify
        # `sqlite_master` directly whatever the authorizer says, and the
        # `PRAGMA` that would lift that refusal is denied below. Read-only
        # connections have no use for the catalogue and do not get it.
        if first == _SCHEMA_TABLE and action in _CATALOGUE_ACTIONS:
            return sqlite3.SQLITE_OK if may_write else sqlite3.SQLITE_DENY

        if action in _READ_ACTIONS:
            return sqlite3.SQLITE_OK if first == table else sqlite3.SQLITE_DENY

        if action in _WRITE_ACTIONS:
            return sqlite3.SQLITE_OK if may_write and first == table else sqlite3.SQLITE_DENY

        # Note the argument order: the table is the *second* argument here.
        if action == sqlite3.SQLITE_ALTER_TABLE:
            return sqlite3.SQLITE_OK if may_write and second == table else sqlite3.SQLITE_DENY

        # Creating, dropping, attaching, reindexing, and anything a future
        # SQLite invents: none of it belongs to a caller.
        return sqlite3.SQLITE_DENY

    return authorize


def is_refusal(*, error: sqlite3.DatabaseError) -> bool:
    """Report whether `error` is the authorizer refusing rather than a failure.

    SQLite raises the same exception class either way, and words a refusal
    three different ways depending on what was refused - "not authorized",
    "access to x.y is prohibited", "authorization denied". The error *code* is
    the same for all of them, so that is what is read here rather than the
    message.

    Args:
        error: The error raised while compiling or running a statement.

    Returns:
        bool: True if the statement was refused as beyond the privilege given.
    """
    # Errors raised by the Python layer rather than by SQLite - sending two
    # statements at once, for one - carry no code at all.
    return getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_AUTH
