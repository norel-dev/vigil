"""The platform's own database: how it is reached, and how it is kept current.

`engine` opens connections to it. `migrations` brings its schema up to the
latest revision. Everything above works with a `Session` and never learns
which database is behind it, nor that Alembic exists.

This is the metadata database — the one holding users, projects and the
records of what a project has put in a datastore. The datastores themselves
are somebody else's storage, and are reached through
`src.features.datastores`.
"""
