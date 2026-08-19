"""Tests of the administrator the configuration puts on a fresh platform.

Every other way of creating a user needs an administrator to already exist, so
without this there would be no first one and an empty database would stay
empty forever. That makes bootstrapping a way in that runs on every start,
from a file, before anybody has authenticated - and the tests here are mostly
about the ways that must *not* be abusable.

The case worth reading first is
`test_putting_a_revoked_key_back_in_the_configuration_is_refused`: rotating a
key away and then rolling the configuration back would otherwise quietly
reinstate a withdrawn credential, which is the one thing revoking exists to
prevent.
"""

from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from src.features.users.model import User
from src.identity import service as api_keys_service
from src.identity.bootstrap import BOOTSTRAP_KEY_NAME, ensure_bootstrap_admins
from src.identity.keys import generate_key
from src.identity.model import ApiKey
from src.platform.config import AuthConfig, BootstrapAdminConfig
from src.platform.exceptions import ConfigurationError, InvalidApiKeyError
from tests.conftest import api_key_for


def _admins_holding(
    *, key: str, email: str = "ops@example.com", name: str = "Ops"
) -> list[BootstrapAdminConfig]:
    """Return the configuration for a single bootstrap administrator.

    Args:
        key: The key the configuration gives them.
        email: Address they are known by.
        name: Their display name.

    Returns:
        list[BootstrapAdminConfig]: A one entry bootstrap list.
    """
    return [BootstrapAdminConfig(email=email, name=name, api_key=key)]


# --- the way in -------------------------------------------------------------


def test_the_configured_administrator_can_call_a_fresh_platform(
    engine: Engine,
) -> None:
    """An empty database still has a way in, or nothing could ever be created."""
    key = generate_key()

    ensure_bootstrap_admins(engine=engine, admins=_admins_holding(key=key))

    with Session(engine) as session:
        user = api_keys_service.authenticate(session=session, key=key)
        assert user.email == "ops@example.com"
        assert user.is_platform_admin is True


def test_starting_twice_does_not_issue_a_second_key(engine: Engine) -> None:
    """The API bootstraps on every start, so doing it twice has to be harmless."""
    admins = _admins_holding(key=generate_key())

    ensure_bootstrap_admins(engine=engine, admins=admins)
    ensure_bootstrap_admins(engine=engine, admins=admins)

    with Session(engine) as session:
        assert len(session.exec(select(ApiKey)).all()) == 1
        assert len(session.exec(select(User)).all()) == 1


def test_configuring_no_administrator_at_all_is_allowed(engine: Engine) -> None:
    """A platform that already has one does not need the file to name another."""
    ensure_bootstrap_admins(engine=engine, admins=[])

    with Session(engine) as session:
        assert session.exec(select(User)).all() == []


def test_an_existing_user_named_in_the_configuration_is_promoted(
    engine: Engine, callers: dict[str, UUID]
) -> None:
    """Naming somebody who already exists makes them an administrator."""
    key = generate_key()

    ensure_bootstrap_admins(
        engine=engine,
        admins=_admins_holding(key=key, email="alice@example.com", name="Alice"),
    )

    with Session(engine) as session:
        assert api_keys_service.authenticate(session=session, key=key).is_platform_admin
        # Her own key still works: the configuration adds a way in, it does
        # not replace the ones she already had.
        assert api_keys_service.authenticate(
            session=session, key=api_key_for(caller="alice")
        )


# --- rotating the key -------------------------------------------------------


def test_changing_the_configured_key_rotates_it(engine: Engine) -> None:
    """Rotating the way in is a config change and a restart, not a repair."""
    old_key = generate_key()
    new_key = generate_key()

    ensure_bootstrap_admins(engine=engine, admins=_admins_holding(key=old_key))
    ensure_bootstrap_admins(engine=engine, admins=_admins_holding(key=new_key))

    with Session(engine) as session:
        assert api_keys_service.authenticate(session=session, key=new_key)

        with pytest.raises(InvalidApiKeyError):
            api_keys_service.authenticate(session=session, key=old_key)

        superseded = session.exec(
            select(ApiKey).where(ApiKey.name == BOOTSTRAP_KEY_NAME)
        ).all()
        assert len(superseded) == 2


def test_putting_a_revoked_key_back_in_the_configuration_is_refused(
    engine: Engine,
) -> None:
    """A withdrawn credential does not come back by being asked for again.

    Rolling the configuration back to a key that was rotated away would
    otherwise quietly reinstate it, which is the one thing revoking is
    supposed to prevent. The process refuses to start instead.
    """
    old_key = generate_key()

    ensure_bootstrap_admins(engine=engine, admins=_admins_holding(key=old_key))
    ensure_bootstrap_admins(engine=engine, admins=_admins_holding(key=generate_key()))

    with pytest.raises(ConfigurationError, match="revoked"):
        ensure_bootstrap_admins(engine=engine, admins=_admins_holding(key=old_key))


def test_giving_an_administrator_somebody_elses_key_is_refused(
    engine: Engine, callers: dict[str, UUID]
) -> None:
    """One key means one caller, so it cannot be handed to a second."""
    with pytest.raises(ConfigurationError, match="another user"):
        ensure_bootstrap_admins(
            engine=engine, admins=_admins_holding(key=api_key_for(caller="alice"))
        )


# --- what the configuration will not describe -------------------------------


def test_two_administrators_may_not_share_an_address() -> None:
    """An address names one user, so two entries for it describe nobody clearly."""
    key, other_key = generate_key(), generate_key()

    with pytest.raises(ValueError, match="share an address"):
        AuthConfig(
            bootstrap_platform_admins=[
                BootstrapAdminConfig(email="ops@example.com", name="Ops", api_key=key),
                BootstrapAdminConfig(
                    email="ops@example.com", name="Ops Again", api_key=other_key
                ),
            ]
        )


def test_two_administrators_may_not_share_a_key() -> None:
    """A key identifies who acted, which a shared one could no longer do."""
    shared = generate_key()

    with pytest.raises(ValueError, match="share an key"):
        AuthConfig(
            bootstrap_platform_admins=[
                BootstrapAdminConfig(email="ops@example.com", name="Ops", api_key=shared),
                BootstrapAdminConfig(
                    email="sre@example.com", name="Sre", api_key=shared
                ),
            ]
        )


def test_a_configuration_naming_two_distinct_administrators_is_accepted() -> None:
    """The check refuses collisions, not the plural itself."""
    config = AuthConfig(
        bootstrap_platform_admins=[
            BootstrapAdminConfig(
                email="ops@example.com", name="Ops", api_key=generate_key()
            ),
            BootstrapAdminConfig(
                email="sre@example.com", name="Sre", api_key=generate_key()
            ),
        ]
    )

    assert len(config.bootstrap_platform_admins) == 2
