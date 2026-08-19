"""End to end tests of who exists on the platform, and who decides that.

Creating a user, listing them and issuing somebody a replacement key are all
administrator work, and they are gathered here rather than with the API key
tests because what they pin down is the administrator's reach rather than the
credential itself. `tests/test_api_keys.py` covers what a key is and what a
caller may do with their own.

The case worth reading first is
`test_an_administrator_can_issue_a_key_to_somebody_who_lost_theirs`, because
it is the only way back for a user with no working credential at all, and so
the one piece of this that has to keep working when everything else has
failed for them.
"""

from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.conftest import headers_for, make_platform_admin, user_id_of

# --- who exists -------------------------------------------------------------


def test_a_platform_administrator_creates_a_user_who_can_then_call(
    client: TestClient, session: Session
) -> None:
    """A new user arrives with a key, and the key works."""
    make_platform_admin(session=session, email="root@example.com")

    created = client.post(
        "/users/",
        json={"email": "carol@example.com", "name": "Carol"},
        headers=headers_for(caller="root"),
    )

    assert created.status_code == httpx.codes.CREATED, created.text
    key = created.json()["api_key"]["api_key"]

    response = client.get("/users/me", headers={"Authorization": f"Bearer {key}"})
    assert response.status_code == httpx.codes.OK, response.text
    assert response.json()["email"] == "carol@example.com"
    assert response.json()["is_platform_admin"] is False


def test_a_regular_user_may_not_create_a_user(client: TestClient) -> None:
    """Who exists on the platform is the platform's own business."""
    response = client.post(
        "/users/",
        json={"email": "carol@example.com", "name": "Carol"},
        headers=headers_for(caller="alice"),
    )

    assert response.status_code == httpx.codes.FORBIDDEN, response.text
    assert "only platform administrators" in response.json()["reason"]


def test_an_address_can_only_be_held_by_one_user(
    client: TestClient, session: Session
) -> None:
    """Membership is granted by address, so two users cannot share one."""
    make_platform_admin(session=session, email="root@example.com")

    response = client.post(
        "/users/",
        json={"email": "alice@example.com", "name": "Not Alice"},
        headers=headers_for(caller="root"),
    )

    assert response.status_code == httpx.codes.CONFLICT, response.text


def test_an_address_that_is_not_an_address_is_refused(
    client: TestClient, session: Session
) -> None:
    """The address is what a user is later granted a project by, so it is checked."""
    make_platform_admin(session=session, email="root@example.com")

    response = client.post(
        "/users/",
        json={"email": "carol-at-example", "name": "Carol"},
        headers=headers_for(caller="root"),
    )

    assert response.status_code == httpx.codes.UNPROCESSABLE_ENTITY, response.text


# --- the listing ------------------------------------------------------------


def test_a_regular_user_sees_no_users_in_the_listing(client: TestClient) -> None:
    """A listing is filtered by the policy rather than refused by it."""
    response = client.get("/users/", headers=headers_for(caller="alice"))

    assert response.status_code == httpx.codes.OK, response.text
    assert response.json() == []


def test_a_platform_administrator_sees_every_user(
    client: TestClient, session: Session
) -> None:
    """The same listing, for somebody the policy trusts everywhere."""
    make_platform_admin(session=session, email="root@example.com")

    response = client.get("/users/", headers=headers_for(caller="root"))

    assert response.status_code == httpx.codes.OK, response.text
    assert {user["email"] for user in response.json()} == {
        "alice@example.com",
        "bob@example.com",
        "root@example.com",
    }


# --- issuing somebody else a key --------------------------------------------


def test_an_administrator_can_issue_a_key_to_somebody_who_lost_theirs(
    client: TestClient, session: Session
) -> None:
    """This is the way back for a user with no working key at all."""
    make_platform_admin(session=session, email="root@example.com")
    alice_id = user_id_of(client=client, caller="alice")

    issued = client.post(
        f"/users/{alice_id}/api-keys",
        json={"name": "replacement"},
        headers=headers_for(caller="root"),
    )

    assert issued.status_code == httpx.codes.CREATED, issued.text
    response = client.get(
        "/users/me", headers={"Authorization": f"Bearer {issued.json()['api_key']}"}
    )
    assert response.json()["email"] == "alice@example.com"


def test_a_regular_user_may_not_issue_a_key_for_anybody(client: TestClient) -> None:
    """Not for somebody else, and not for themselves through this door.

    A key issued here acts as its holder, so handing one out is as far
    reaching as anything on the platform. Alice asking for one against her own
    record is refused just the same, because this endpoint is the one that
    reaches other people.
    """
    alice_id = user_id_of(client=client, caller="alice")
    bob_id = user_id_of(client=client, caller="bob")

    for target in (alice_id, bob_id):
        response = client.post(
            f"/users/{target}/api-keys",
            json={"name": "mine now"},
            headers=headers_for(caller="alice"),
        )
        assert response.status_code == httpx.codes.FORBIDDEN, response.text


def test_issuing_a_key_to_somebody_who_does_not_exist_is_a_404(
    client: TestClient, session: Session
) -> None:
    """A key that acts as nobody is never created; the id is reported missing."""
    make_platform_admin(session=session, email="root@example.com")

    response = client.post(
        f"/users/{uuid4()}/api-keys",
        json={"name": "for a ghost"},
        headers=headers_for(caller="root"),
    )

    assert response.status_code == httpx.codes.NOT_FOUND, response.text
    assert "user" in response.json()["detail"]
