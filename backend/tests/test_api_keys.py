"""End to end tests of authenticating with an API key.

These go through the real application, so what they pin down is the whole
path: a key comes back from an endpoint, is sent on the next request, and
decides who the platform thinks is calling.

What this file covers is the credential itself - what a key is, what a caller
may do with their own, and what is left in the database afterwards. Issuing
one to somebody else is administrator work and lives in
`tests/test_user_administration.py`; the key the configuration puts on an
empty platform lives in `tests/test_bootstrap_admin.py`.

The cases worth reading first are the ones about keys that should stop
working - `test_a_revoked_key_stops_working` and
`test_an_expired_key_is_refused` - because everything else on the platform
rests on a withdrawn credential actually being withdrawn.
"""

from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.features.users.model import User
from src.identity.keys import digest_of, generate_key
from src.identity.model import ApiKey
from tests.conftest import headers_for

#: A key that is well formed and was never issued.
UNKNOWN_KEY = "dpk_a_key_this_platform_has_never_issued_00000"


def _issue_key(*, client: TestClient, caller: str, name: str = "second") -> str:
    """Ask the API for another key for `caller` and return it.

    Args:
        client: The test client.
        caller: The name of the caller asking.
        name: What to call the new key.

    Returns:
        str: The key that came back.
    """
    response = client.post(
        "/users/me/api-keys",
        json={"name": name},
        headers=headers_for(caller=caller),
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    return str(response.json()["api_key"])


# --- what a key is ----------------------------------------------------------


def test_two_generated_keys_are_never_the_same() -> None:
    """A key is randomness, not a name derived from anything."""
    assert generate_key() != generate_key()


def test_a_key_is_recognisable_as_this_platforms() -> None:
    """Whoever finds one in a log can tell where it came from."""
    assert generate_key().startswith("dpk_")


# --- using one --------------------------------------------------------------


def test_a_key_identifies_the_caller_behind_it(client: TestClient) -> None:
    """The happy path: a key is presented, and the platform knows who it is."""
    response = client.get("/users/me", headers=headers_for(caller="alice"))

    assert response.status_code == httpx.codes.OK, response.text
    assert response.json()["email"] == "alice@example.com"


def test_a_request_without_a_key_is_refused(client: TestClient) -> None:
    """Everything below the health endpoint needs a caller."""
    response = client.get("/users/me")

    assert response.status_code == httpx.codes.UNAUTHORIZED, response.text
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_a_key_the_platform_never_issued_is_refused(client: TestClient) -> None:
    """A well formed key is worth nothing without a row behind it."""
    response = client.get(
        "/users/me", headers={"Authorization": f"Bearer {UNKNOWN_KEY}"}
    )

    assert response.status_code == httpx.codes.UNAUTHORIZED, response.text


def test_the_health_endpoint_needs_no_key(client: TestClient) -> None:
    """Whether the API is up is not a question about who is asking."""
    assert client.get("/").status_code == httpx.codes.OK


# --- managing your own ------------------------------------------------------


def test_a_caller_can_issue_themselves_another_key(client: TestClient) -> None:
    """Rotating a key means creating the next one and moving over to it."""
    second = _issue_key(client=client, caller="alice")

    response = client.get("/users/me", headers={"Authorization": f"Bearer {second}"})

    assert response.status_code == httpx.codes.OK, response.text
    assert response.json()["email"] == "alice@example.com"


def test_a_key_is_shown_once_and_never_again(client: TestClient) -> None:
    """The listing describes keys; it cannot hand any of them back."""
    secret = _issue_key(client=client, caller="alice")

    listed = client.get("/users/me/api-keys", headers=headers_for(caller="alice"))

    assert listed.status_code == httpx.codes.OK, listed.text
    assert secret not in listed.text
    assert {key["name"] for key in listed.json()} == {"test", "second"}


def test_a_revoked_key_stops_working(client: TestClient) -> None:
    """Withdrawing a key is what makes a leaked one survivable."""
    secret = _issue_key(client=client, caller="alice")
    issued = client.get("/users/me/api-keys", headers=headers_for(caller="alice")).json()
    key_id = next(key["id"] for key in issued if key["name"] == "second")

    revoked = client.delete(
        f"/users/me/api-keys/{key_id}", headers=headers_for(caller="alice")
    )

    assert revoked.status_code == httpx.codes.OK, revoked.text
    assert revoked.json()["revocation_date"] is not None

    refused = client.get("/users/me", headers={"Authorization": f"Bearer {secret}"})
    assert refused.status_code == httpx.codes.UNAUTHORIZED, refused.text


def test_a_revoked_key_is_kept_rather_than_deleted(client: TestClient) -> None:
    """What existed stays answerable after the fact."""
    _issue_key(client=client, caller="alice")
    issued = client.get("/users/me/api-keys", headers=headers_for(caller="alice")).json()
    key_id = next(key["id"] for key in issued if key["name"] == "second")

    client.delete(f"/users/me/api-keys/{key_id}", headers=headers_for(caller="alice"))

    listed = client.get("/users/me/api-keys", headers=headers_for(caller="alice")).json()
    assert {key["id"] for key in listed} == {key["id"] for key in issued}


def test_a_caller_cannot_revoke_somebody_elses_key(client: TestClient) -> None:
    """A key id is not a capability: it only works inside its own account."""
    _issue_key(client=client, caller="bob")
    bobs_keys = client.get("/users/me/api-keys", headers=headers_for(caller="bob")).json()
    key_id = next(key["id"] for key in bobs_keys if key["name"] == "second")

    response = client.delete(
        f"/users/me/api-keys/{key_id}", headers=headers_for(caller="alice")
    )

    assert response.status_code == httpx.codes.NOT_FOUND, response.text
    assert client.get("/users/me", headers=headers_for(caller="bob")).status_code == (
        httpx.codes.OK
    )


def test_a_caller_only_sees_their_own_keys(client: TestClient) -> None:
    """One account's keys are no part of another's listing."""
    _issue_key(client=client, caller="bob", name="bobs laptop")

    listed = client.get("/users/me/api-keys", headers=headers_for(caller="alice")).json()

    assert {key["name"] for key in listed} == {"test"}


def test_an_expired_key_is_refused(client: TestClient, session: Session) -> None:
    """A key with a lifetime stops working when the lifetime runs out."""
    secret = _issue_key(client=client, caller="alice")
    stored = session.exec(
        select(ApiKey).where(ApiKey.secret_hash == digest_of(key=secret))
    ).one()
    stored.expiration_date = datetime.now() - timedelta(seconds=1)
    session.add(stored)
    session.commit()

    response = client.get("/users/me", headers={"Authorization": f"Bearer {secret}"})

    assert response.status_code == httpx.codes.UNAUTHORIZED, response.text


def test_a_lifetime_is_recorded_when_one_is_asked_for(client: TestClient) -> None:
    """A key that should not outlive the week can be created that way."""
    response = client.post(
        "/users/me/api-keys",
        json={"name": "temporary", "lifetime_days": 7},
        headers=headers_for(caller="alice"),
    )

    assert response.status_code == httpx.codes.CREATED, response.text
    assert response.json()["expiration_date"] is not None


# --- what is stored ---------------------------------------------------------


def test_the_key_itself_is_never_stored(client: TestClient, session: Session) -> None:
    """A copy of the table is of no use to whoever takes it."""
    secret = _issue_key(client=client, caller="alice")

    stored = session.exec(select(ApiKey)).all()

    assert secret not in [key.secret_hash for key in stored]
    assert digest_of(key=secret) in [key.secret_hash for key in stored]


def test_a_user_holding_a_key_cannot_be_deleted_out_from_under_it(
    engine: Engine,
) -> None:
    """A key can never outlive its user, so no key ever resolves to nobody."""
    with Session(engine) as session:
        user = User(email="gone@example.com", name="Gone")
        session.add(user)
        session.add(
            ApiKey(user_id=user.id, name="theirs", secret_hash=digest_of(key=generate_key()))
        )
        session.commit()

        session.delete(user)
        with pytest.raises(IntegrityError):
            session.commit()
