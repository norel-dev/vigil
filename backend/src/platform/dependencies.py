"""FastAPI dependencies that hand request handlers what they need.

This module is the only place that knows the long lived components hang off
the application object; everything else asks for them by type.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from src.authz.enforcement import AccessEnforcer
from src.database.engine import open_session
from src.platform.config import AppConfig
from src.platform.state import ApplicationServices

__all__ = [
    "Configuration",
    "DatabaseSession",
    "Enforcer",
    "Services",
    "get_configuration",
    "get_enforcer",
    "get_services",
    "get_session",
]


def get_services(request: Request) -> ApplicationServices:
    """Return the components the application was built with.

    Args:
        request: The request being handled.

    Returns:
        ApplicationServices: The process wide components.
    """
    return request.app.state.services


def get_session(
    services: Annotated[ApplicationServices, Depends(get_services)],
) -> Iterator[Session]:
    """Yield a database session for the duration of the request.

    Args:
        services: The process wide components.

    Yields:
        Session: A session that is closed when the request ends.
    """
    yield from open_session(engine=services.engine)


def get_enforcer(
    services: Annotated[ApplicationServices, Depends(get_services)],
) -> AccessEnforcer:
    """Return the component that refuses disallowed actions.

    Args:
        services: The process wide components.

    Returns:
        AccessEnforcer: The enforcer bound to the configured policy engine.
    """
    return services.enforcer


def get_configuration(
    services: Annotated[ApplicationServices, Depends(get_services)],
) -> AppConfig:
    """Return the configuration the process was started with.

    Args:
        services: The process wide components.

    Returns:
        AppConfig: The active configuration.
    """
    return services.config


Services = Annotated[ApplicationServices, Depends(get_services)]
DatabaseSession = Annotated[Session, Depends(get_session)]
Enforcer = Annotated[AccessEnforcer, Depends(get_enforcer)]
Configuration = Annotated[AppConfig, Depends(get_configuration)]
