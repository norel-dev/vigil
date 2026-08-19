"""What every datastore implementation has to offer, and nothing more.

This is deliberately the smallest base there could be. An implementation says
what shape of data it holds and can be queried directly by a platform
administrator; everything else it can do - holding tables, holding blobs - is
declared by satisfying a protocol that lives with the feature it serves
(`src.features.tables.storage`, `src.features.blobs.storage`), not by
inheriting from here. That is what keeps a store that holds blobs from having
to stub out methods about tables.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from src.features.datastores.storage import DataStoreQuery, DataStoreQueryResponse, DataType

__all__ = ["DataStoreImplementationBase"]


class DataStoreImplementationBase(BaseModel, ABC):
    """Base class for every datastore implementation.

    A concrete implementation declares its own connection fields and
    implements `query`. The `implementation` literal is the discriminator
    that selects the implementation in the create-datastore request body,
    and that rebuilds it from the stored connection details.
    """

    implementation: str

    @abstractmethod
    async def get_data_type(self) -> DataType:
        """Return the datatype of the implementation"""

    @abstractmethod
    async def query(self, query: DataStoreQuery) -> DataStoreQueryResponse:
        """Run a query against the datastore."""
