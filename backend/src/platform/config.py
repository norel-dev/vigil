"""Application configuration, loaded from a YAML file.

Configuration is read exactly once, at process start, and is then injected
into the components that need it. Nothing in this package reads environment
variables or hardcodes deployment specific values; the only decision made
outside this module is *which* YAML file to load.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator
from sqlalchemy import make_url
from sqlalchemy.exc import ArgumentError

from src.platform.exceptions import ConfigurationError

__all__ = [
    "AppConfig",
    "AuthConfig",
    "BootstrapAdminConfig",
    "DatabaseConfig",
    "OpaConfig",
    "load_config",
]

#: Shortest key the configuration will accept for a bootstrap administrator.
#: Nothing shorter carries enough randomness to be worth guessing at, and a
#: key somebody typed by hand is usually shorter than this.
MINIMUM_BOOTSTRAP_KEY_LENGTH = 32


#: The only SQLAlchemy driver the metadata database is reached through.
METADATA_DATABASE_DRIVER = "postgresql+psycopg"


class DatabaseConfig(BaseModel):
    """How to reach the metadata database, which is always PostgreSQL."""

    url: str = Field(
        description="SQLAlchemy URL of the PostgreSQL database holding the platform metadata.",
        examples=["postgresql+psycopg://dataplatform:secret@localhost:5432/dataplatform"],
    )
    echo: bool = Field(
        default=False,
        description="Whether SQLAlchemy should log every statement it emits.",
    )

    @field_validator("url")
    @classmethod
    def _check_url_is_postgresql(cls, url: str) -> str:
        """Reject a URL for any database other than PostgreSQL.

        The migrations and the constraints the platform relies on are written
        for PostgreSQL alone, so a URL for anything else would start a process
        that misbehaves later rather than one that fails now.

        Args:
            url: The configured URL.

        Returns:
            str: The URL, unchanged.

        Raises:
            ValueError: If the URL cannot be parsed or names another database
                or driver.
        """
        try:
            driver = make_url(url).drivername
        except ArgumentError as error:
            raise ValueError(f"not a database URL: {error}") from error

        if driver != METADATA_DATABASE_DRIVER:
            raise ValueError(
                f"the metadata database must be PostgreSQL, reached as "
                f"'{METADATA_DATABASE_DRIVER}://...', not '{driver}://...'"
            )

        return url


class BootstrapAdminConfig(BaseModel):
    """A platform administrator the process brings into being as it starts.

    Every other user and every other key is created through the API, and
    creating them takes an administrator, so the platform has to arrive with
    one already holding a usable key. That is what this is: the one credential
    that comes from configuration rather than from the API.
    """

    email: EmailStr = Field(description="Address this administrator is known by.")
    name: str = Field(description="Their display name.")
    api_key: str = Field(
        min_length=MINIMUM_BOOTSTRAP_KEY_LENGTH,
        description=(
            "The key this administrator authenticates with. It is a secret in "
            "the same sense a password is, so it belongs in whatever holds the "
            "deployment's secrets rather than in a file under version control."
        ),
    )


class AuthConfig(BaseModel):
    """How callers are authenticated."""

    bootstrap_platform_admins: list[BootstrapAdminConfig] = Field(
        default_factory=list,
        description=(
            "Administrators that exist as soon as the platform starts, each "
            "with the key they call it with. Leaving this empty leaves nobody "
            "able to register a datastore or create a user."
        ),
    )

    @field_validator("bootstrap_platform_admins")
    @classmethod
    def _check_admins_are_distinct(
        cls, admins: list[BootstrapAdminConfig]
    ) -> list[BootstrapAdminConfig]:
        """Reject a list where two administrators are the same person or key.

        A key identifies exactly one caller, so two administrators sharing one
        would leave the platform unable to say which of them acted.

        Args:
            admins: The administrators the configuration declares.

        Returns:
            list[BootstrapAdminConfig]: The list, unchanged.

        Raises:
            ValueError: If an address or a key appears more than once.
        """
        for field, values in (
            ("address", [admin.email for admin in admins]),
            ("key", [admin.api_key for admin in admins]),
        ):
            if len(set(values)) != len(values):
                raise ValueError(
                    f"Two bootstrap platform administrators share an {field}; "
                    "each one needs their own"
                )

        return admins


class OpaConfig(BaseModel):
    """How to reach the Open Policy Agent that renders access decisions."""

    url: str = Field(
        default="http://localhost:8181",
        description="Base URL of the OPA server.",
    )
    decision_path: str = Field(
        default="dataplatform/authz/decision",
        description=(
            "Data API path of the rule that renders a single decision, "
            "without the leading '/v1/data/'."
        ),
    )
    filter_path: str = Field(
        default="dataplatform/authz/allowed_resource_ids",
        description=(
            "Data API path of the rule that filters a list of resources, "
            "without the leading '/v1/data/'."
        ),
    )
    request_timeout_seconds: float = Field(
        default=2.0,
        gt=0,
        description="Timeout for a single decision request.",
    )


class AppConfig(BaseModel):
    """The full configuration of the API process."""

    database: DatabaseConfig
    auth: AuthConfig
    opa: OpaConfig


def load_config(*, path: Path) -> AppConfig:
    """Read and validate the YAML configuration file at `path`.

    Args:
        path: Location of the YAML configuration file.

    Returns:
        AppConfig: The validated configuration.

    Raises:
        ConfigurationError: If the file is missing, is not valid YAML, does
            not contain a mapping, or does not satisfy the schema.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(f"Could not read config file {path}: {error}") from error

    try:
        document: Any = yaml.safe_load(raw_text)
    except yaml.YAMLError as error:
        raise ConfigurationError(f"Config file {path} is not valid YAML: {error}") from error

    if not isinstance(document, dict):
        raise ConfigurationError(f"Config file {path} must contain a YAML mapping")

    try:
        return AppConfig.model_validate(document)
    except ValidationError as error:
        raise ConfigurationError(f"Config file {path} is invalid:\n{error}") from error
