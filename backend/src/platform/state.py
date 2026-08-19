"""The long lived components a request may need.

These are built once, when the process starts, and are reached from a request
through `src.platform.dependencies`. Grouping them in one typed object keeps the rest
of the code from poking at loosely typed attributes of `app.state`.
"""

from dataclasses import dataclass

from sqlalchemy import Engine

from src.authz.enforcement import AccessEnforcer
from src.platform.config import AppConfig

__all__ = ["ApplicationServices"]


@dataclass(frozen=True)
class ApplicationServices:
    """Everything a request handler may need that outlives a single request.

    Attributes:
        config: The configuration the process was started with.
        engine: The engine of the metadata database.
        enforcer: Refuses actions the policy does not allow.
    """

    config: AppConfig
    engine: Engine
    enforcer: AccessEnforcer
