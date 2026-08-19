"""Which configuration file this process should read.

The API and the migration tool are two separate entry points into the same
platform, and they have to agree on where the configuration lives. That
agreement is this module: it is the only place that reads the environment,
and both entry points go through it.

Everything below an entry point is handed an `AppConfig` and never learns
where it came from.
"""

import os
from pathlib import Path

from src.platform.config import AppConfig, load_config

__all__ = [
    "CONFIG_PATH_VARIABLE",
    "DEFAULT_CONFIG_PATH",
    "configuration_path",
    "load_configuration",
]

#: Environment variable naming the configuration file to load.
CONFIG_PATH_VARIABLE = "DATAPLATFORM_CONFIG"

#: Configuration file used when the variable above is not set.
DEFAULT_CONFIG_PATH = Path("config.yaml")


def configuration_path() -> Path:
    """Return the configuration file this process was pointed at.

    Returns:
        Path: The path named by the environment, or the default.
    """
    return Path(os.environ.get(CONFIG_PATH_VARIABLE, DEFAULT_CONFIG_PATH))


def load_configuration() -> AppConfig:
    """Load the configuration this process was pointed at.

    Returns:
        AppConfig: The validated configuration.

    Raises:
        ConfigurationError: If the file is missing or does not validate.
    """
    return load_config(path=configuration_path())
