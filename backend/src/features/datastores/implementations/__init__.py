"""The concrete datastore implementations the platform can be built on.

Each implementation lives in a module of its own, because each one changes
for its own reason: a fix to how SQLite hands out privilege has nothing to do
with how MinIO signs a URL, and neither should be able to break the other by
sharing a file. Adding a third store means adding a module here and naming it
in `src.features.datastores.model`, rather than editing anything already working.

What the implementations have in common is not in this package. The base
class they extend is in `base`, and the vocabulary every store is reached by
is in `src.features.datastores.storage`. But *what they can hold* is declared
beside the feature that holds it - `TableStorage` in
`src.features.tables.storage`, `BlobStorage` in `src.features.blobs.storage`
- so that the abstraction does not depend on any of its implementations.
"""

from src.features.datastores.implementations.base import DataStoreImplementationBase
from src.features.datastores.implementations.minio import MinIODataStore
from src.features.datastores.implementations.sqlite import SQLiteDataStore

__all__ = [
    "DataStoreImplementationBase",
    "MinIODataStore",
    "SQLiteDataStore",
]
