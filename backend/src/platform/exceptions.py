"""Custom exceptions raised across the dataplatform API.

Every exception in this module derives from `DataPlatformError`, so callers
that do not care about the specific failure can catch a single type. The
exceptions carry no HTTP semantics on purpose: translating them into
responses is the responsibility of the endpoint layer.
"""

__all__ = [
    "DataPlatformError",
    "ConfigurationError",
    "SchemaMigrationError",
    "ObjectNotFoundError",
    "DuplicateObjectError",
    "AuthenticationError",
    "InvalidApiKeyError",
    "AuthorizationError",
    "PolicyDecisionPointError",
    "PermissionDeniedError",
    "StorageError",
    "UnsuitableDataStoreError",
    "TableProvisioningError",
    "BlobProvisioningError",
    "QueryRefusedError",
    "QueryFailedError",
]


class DataPlatformError(Exception):
    """Base class for every error raised by the dataplatform API."""


class ConfigurationError(DataPlatformError):
    """Raised when the application configuration is missing or invalid."""


class SchemaMigrationError(DataPlatformError):
    """Raised when the database could not be brought up to the latest schema."""


class ObjectNotFoundError(DataPlatformError):
    """Raised when a requested object does not exist."""

    def __init__(self, *, object_type: str, identifier: str) -> None:
        """Record what was looked for.

        Args:
            object_type: The kind of object that was searched for.
            identifier: How the caller referred to it.
        """
        super().__init__(f"The {object_type} '{identifier}' was not found")
        self.object_type = object_type
        self.identifier = identifier


class DuplicateObjectError(DataPlatformError):
    """Raised when an object would take a name that is already in use."""

    def __init__(self, *, object_type: str, identifier: str) -> None:
        """Record what was already taken.

        Args:
            object_type: The kind of object being created.
            identifier: The name that was already in use.
        """
        super().__init__(f"A {object_type} called '{identifier}' already exists")
        self.object_type = object_type
        self.identifier = identifier


class AuthenticationError(DataPlatformError):
    """Base class for failures to establish who the caller is."""


class InvalidApiKeyError(AuthenticationError):
    """Raised when a request carries no usable API key.

    A missing key, an unknown one, a revoked one and an expired one all land
    here and are reported identically, because telling them apart would tell
    whoever asked something about keys that are not theirs.
    """


class AuthorizationError(DataPlatformError):
    """Base class for failures to establish what the caller may do."""


class PolicyDecisionPointError(AuthorizationError):
    """Raised when the policy decision point could not produce a decision.

    Callers must treat this as a denial: an unreachable or misbehaving
    decision point never results in access being granted.
    """


class PermissionDeniedError(AuthorizationError):
    """Raised when the policy explicitly denied the requested action."""

    def __init__(self, *, action: str, resource: str, reason: str) -> None:
        """Record what was denied so the endpoint layer can report it.

        Args:
            action: The action that was requested.
            resource: A human readable identifier of the target resource.
            reason: The explanation produced by the policy.
        """
        super().__init__(f"{action} on {resource} was denied: {reason}")
        self.action = action
        self.resource = resource
        self.reason = reason


class StorageError(DataPlatformError):
    """Base class for failures coming from the storage behind an object.

    These are failures of the engine holding the data, not of the platform's
    own record of it, which is why they are kept apart from the errors above.
    """


class UnsuitableDataStoreError(StorageError):
    """Raised when a datastore cannot hold the kind of object asked of it.

    Asking a datastore that holds blobs for a table is a mistake in the
    request rather than a fault of the platform, so the caller is told which
    datastore could not do what.
    """

    def __init__(self, *, datastore: str, wanted: str) -> None:
        """Record what was asked of which datastore.

        Args:
            datastore: Name of the datastore that was chosen.
            wanted: The kind of object it was asked to hold.
        """
        super().__init__(f"The datastore '{datastore}' does not hold {wanted}")
        self.datastore = datastore
        self.wanted = wanted


class TableProvisioningError(StorageError):
    """Raised when a table could not be created in or removed from storage."""


class BlobProvisioningError(StorageError):
    """Raised when the object store could not do what the platform asked of it.

    This covers every act the platform performs itself - creating a
    namespace, removing a blob, asking after one, signing a URL - and not what
    happens once a signed URL leaves the platform. A caller whose upload is
    refused hears that from the store directly, because the platform is not in
    the path of it.
    """


class QueryRefusedError(StorageError):
    """Raised when the engine refused a statement as beyond the privilege given.

    This is the engine enforcing the boundary the platform connected within,
    such as an attempt to drop a table or to read one belonging to somebody
    else. It is a denial, not a malfunction.
    """


class QueryFailedError(StorageError):
    """Raised when a statement was allowed but could not be run.

    A syntax error or a reference to a column that does not exist lands here:
    the caller was permitted to ask, and the asking did not work.
    """
