"""Assembly of the API application.

This is the one place where an abstraction is tied to an implementation: the
policy decision point becomes OPA, and the routers are wired up. Every other
module depends only on the interface, so swapping it out happens here alone.

Authentication needs no such seam. A caller presents an API key this platform
issued, and the platform holds the digest of it, so there is nothing external
to stand behind an interface.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from loguru import logger

from src.authz.enforcement import AccessEnforcer
from src.authz.opa import OpaPolicyDecisionPoint
from src.database.engine import create_database_engine
from src.database.migrations import upgrade_to_head
from src.features.blobs.router import create_blobs_router
from src.features.datastores.router import create_datastores_router
from src.features.projects.router import create_projects_router
from src.features.tables.router import create_tables_router
from src.features.users.router import create_users_router
from src.identity.bootstrap import ensure_bootstrap_admins
from src.platform.config import AppConfig
from src.platform.error_handlers import register_error_handlers
from src.platform.state import ApplicationServices

__all__ = ["create_app"]

_API_DESCRIPTION = """
An API for managing a dataplatform.

Callers authenticate with an **API key**, sent as `Authorization: Bearer
<key>`. What they may then do is decided by an Open Policy Agent policy, not
by this API: every request is answered with the caller's project roles, and
OPA works out whether the action is allowed.

Press **Authorize** and paste your key to call anything below.
"""


def create_app(*, config: AppConfig) -> FastAPI:
    """Build the API application from `config`.

    Args:
        config: The configuration the process was started with.

    Returns:
        FastAPI: The application, ready to be served.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Open the resources the application needs, and close them after."""
        engine = create_database_engine(config=config.database)
        upgrade_to_head(engine=engine)
        ensure_bootstrap_admins(
            engine=engine, admins=config.auth.bootstrap_platform_admins
        )

        async with httpx.AsyncClient() as http_client:
            decision_point = OpaPolicyDecisionPoint(config=config.opa, client=http_client)
            if await decision_point.check_reachable():
                logger.info("Open Policy Agent at {} is reachable", config.opa.url)

            app.state.services = ApplicationServices(
                config=config,
                engine=engine,
                enforcer=AccessEnforcer(
                    decision_point=decision_point,
                    resource_filter=decision_point,
                ),
            )
            yield

        engine.dispose()

    app = FastAPI(
        title="DataPlatform API",
        description=_API_DESCRIPTION,
        lifespan=lifespan,
    )

    register_error_handlers(app=app)

    app.include_router(create_users_router())
    app.include_router(create_projects_router())
    app.include_router(create_tables_router())
    app.include_router(create_blobs_router())
    app.include_router(create_datastores_router())

    @app.get("/", tags=["health"])
    async def default() -> str:
        """Report that the API is up. Requires no credentials."""
        return "Ok"

    return app
