"""Entry point of the dataplatform API.

Which configuration file to read is worked out by `src.platform.environment`, which
the migration tool shares, so that serving the API and migrating its database
can never disagree about where the platform is configured.

Serve it with:

    uv run fastapi dev main.py
"""

import sys

from fastapi import FastAPI
from loguru import logger

from src.app import create_app
from src.platform.environment import (
    CONFIG_PATH_VARIABLE,
    DEFAULT_CONFIG_PATH,
    configuration_path,
    load_configuration,
)
from src.platform.exceptions import ConfigurationError


def main() -> FastAPI:
    """Load the configuration and build the application.

    Returns:
        FastAPI: The application to serve.

    Raises:
        SystemExit: If the configuration could not be loaded, since there is
            nothing sensible to serve without it.
    """
    config_path = configuration_path()

    try:
        config = load_configuration()
    except ConfigurationError as error:
        logger.error("{}", error)
        logger.error(
            "Copy config.example.yaml to {} and fill it in, or point {} at "
            "another file.",
            DEFAULT_CONFIG_PATH,
            CONFIG_PATH_VARIABLE,
        )
        sys.exit(1)

    logger.info("Loaded configuration from {}", config_path)
    return create_app(config=config)


app = main()
