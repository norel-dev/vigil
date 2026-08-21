"""End to end tests of who may reach which project.

Projects are the level users own: any user of the platform may create one,
and from then on the role they hold decides what they may do. What is pinned down here
is the membership model itself; `test_table_access.py` covers how the objects
inside a project inherit it.
"""

from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.conftest import headers_for, make_platform_admin


def _create_project(*, client: TestClient, caller: str, name: str) -> str:
    """Create a project owned by `caller` and return its id.

    Args:
        client: The test client.
        caller: The name of the caller creating it.
        name: Name of the new project.

    Returns:
        str: The id of the created project.
    """
    response = client.post(
        "/projects/",
        json={"name": name, "description": None},
        headers=headers_for(caller=caller),
    )
    assert response.status_code == httpx.codes.CREATED, response.text
    return str(response.json()["id"])


def _grant(*, client: TestClient, project_id: str, caller: str, email: str, role: str):
    """Give `email` the role `role` in a project, as `caller`.

    Args:
        client: The test client.
        project_id: The project the role is held in.
        caller: The name of the caller granting it.
        email: Address of the user being granted the role.
        role: The role to grant.

    Returns:
        httpx.Response: What the platform answered, refusals included, so that
            a test can assert on one.
    """
    return client.put(
        f"/projects/{project_id}/members",
        json={"email": email, "role": role},
        headers=headers_for(caller=caller),
    )


# --- reaching a project -----------------------------------------------------


def test_any_user_of_the_platform_may_create_a_project(client: TestClient) -> None:
    """Creating a project needs nothing but a working key."""
    project_id = _create_project(client=client, caller="alice", name="alices project")

    read_back = client.get(f"/projects/{project_id}", headers=headers_for(caller="alice"))
    assert read_back.status_code == httpx.codes.OK, read_back.text


def test_a_project_is_invisible_to_outsiders(client: TestClient) -> None:
    """Bob's project is not Alice's to read, and does not show up in her listing."""
    bobs_project = _create_project(client=client, caller="bob", name="bobs project")

    direct = client.get(f"/projects/{bobs_project}", headers=headers_for(caller="alice"))
    assert direct.status_code == httpx.codes.FORBIDDEN, direct.text
    assert "is not a member of the project" in direct.json()["reason"]

    listed = client.get("/projects/", headers=headers_for(caller="alice"))
    assert listed.status_code == httpx.codes.OK, listed.text
    assert listed.json() == []


# --- membership -------------------------------------------------------------


def test_membership_is_what_opens_access(client: TestClient) -> None:
    """Once Bob invites Alice as a viewer, the same read starts working."""
    bobs_project = _create_project(client=client, caller="bob", name="bobs project")

    refused = client.get(f"/projects/{bobs_project}", headers=headers_for(caller="alice"))
    assert refused.status_code == httpx.codes.FORBIDDEN

    granted = client.put(
        f"/projects/{bobs_project}/members",
        json={"email": "alice@example.com", "role": "viewer"},
        headers=headers_for(caller="bob"),
    )
    assert granted.status_code == httpx.codes.OK, granted.text

    allowed = client.get(f"/projects/{bobs_project}", headers=headers_for(caller="alice"))
    assert allowed.status_code == httpx.codes.OK, allowed.text


def test_a_viewer_still_cannot_manage_members(client: TestClient) -> None:
    """Being let in is not the same as being given everything."""
    bobs_project = _create_project(client=client, caller="bob", name="bobs project")
    client.put(
        f"/projects/{bobs_project}/members",
        json={"email": "alice@example.com", "role": "viewer"},
        headers=headers_for(caller="bob"),
    )

    response = client.put(
        f"/projects/{bobs_project}/members",
        json={"email": "alice@example.com", "role": "owner"},
        headers=headers_for(caller="alice"),
    )

    assert response.status_code == httpx.codes.FORBIDDEN, response.text
    assert "viewer" in response.json()["reason"]


def test_outsiders_cannot_invite_themselves(client: TestClient) -> None:
    """Membership can only be granted by someone who already administers it."""
    bobs_project = _create_project(client=client, caller="bob", name="bobs project")

    response = client.put(
        f"/projects/{bobs_project}/members",
        json={"email": "alice@example.com", "role": "owner"},
        headers=headers_for(caller="alice"),
    )

    assert response.status_code == httpx.codes.FORBIDDEN, response.text


def test_platform_administrators_reach_every_project(
    client: TestClient, session: Session
) -> None:
    """The platform administrator flag bypasses project membership."""
    make_platform_admin(session=session, email="root@example.com")
    bobs_project = _create_project(client=client, caller="bob", name="bobs project")

    response = client.get(f"/projects/{bobs_project}", headers=headers_for(caller="root"))

    assert response.status_code == httpx.codes.OK, response.text


def test_a_project_that_does_not_exist_is_a_404_rather_than_a_refusal(
    client: TestClient,
) -> None:
    """Nothing exists to be a member of, so there is no membership to report on."""
    response = client.get(f"/projects/{uuid4()}", headers=headers_for(caller="alice"))

    assert response.status_code == httpx.codes.NOT_FOUND, response.text
    assert "project" in response.json()["detail"]


def test_granting_a_role_to_an_address_nobody_holds_is_a_404(
    client: TestClient,
) -> None:
    """A membership for a user who does not exist would let nobody in."""
    project_id = _create_project(client=client, caller="alice", name="alices project")

    response = _grant(
        client=client,
        project_id=project_id,
        caller="alice",
        email="nobody@example.com",
        role="viewer",
    )

    assert response.status_code == httpx.codes.NOT_FOUND, response.text
    assert "nobody@example.com" in response.json()["detail"]


def test_granting_a_second_role_replaces_the_first(client: TestClient) -> None:
    """A user holds one role in a project, so granting again moves them.

    The alternative - two memberships, each with its own role - would leave
    the policy with two answers to what Alice may do here, and no rule for
    choosing between them.
    """
    project_id = _create_project(client=client, caller="bob", name="bobs project")
    _grant(
        client=client,
        project_id=project_id,
        caller="bob",
        email="alice@example.com",
        role="viewer",
    )

    promoted = _grant(
        client=client,
        project_id=project_id,
        caller="bob",
        email="alice@example.com",
        role="editor",
    )

    assert promoted.status_code == httpx.codes.OK, promoted.text
    assert promoted.json()["role"] == "editor"

    listed = client.get(
        f"/projects/{project_id}/members", headers=headers_for(caller="bob")
    )
    alices = [entry for entry in listed.json() if entry["email"] == "alice@example.com"]
    assert len(alices) == 1
    assert alices[0]["role"] == "editor"


# --- the limits on changing membership --------------------------------------


def test_an_admin_may_grant_every_role_below_owner(client: TestClient) -> None:
    """Managing members is still most of what an admin was let in to do."""
    project_id = _create_project(client=client, caller="bob", name="bobs project")
    _grant(
        client=client,
        project_id=project_id,
        caller="bob",
        email="alice@example.com",
        role="admin",
    )

    for role in ("viewer", "editor", "admin"):
        response = _grant(
            client=client,
            project_id=project_id,
            caller="alice",
            email="root@example.com",
            role=role,
        )
        assert response.status_code == httpx.codes.OK, response.text
        assert response.json()["role"] == role


def test_an_admin_may_not_promote_anybody_to_owner(client: TestClient) -> None:
    """An admin's reach over membership stops below the role above their own."""
    project_id = _create_project(client=client, caller="bob", name="bobs project")
    _grant(
        client=client,
        project_id=project_id,
        caller="bob",
        email="alice@example.com",
        role="admin",
    )

    response = _grant(
        client=client,
        project_id=project_id,
        caller="alice",
        email="root@example.com",
        role="owner",
    )

    assert response.status_code == httpx.codes.FORBIDDEN, response.text
    assert "only an owner may grant the 'owner' role" in response.json()["reason"]


def test_an_owner_may_promote_somebody_to_owner(client: TestClient) -> None:
    """The role can still be handed out, by somebody who already holds it."""
    project_id = _create_project(client=client, caller="bob", name="bobs project")

    response = _grant(
        client=client,
        project_id=project_id,
        caller="bob",
        email="alice@example.com",
        role="owner",
    )

    assert response.status_code == httpx.codes.OK, response.text
    assert response.json()["role"] == "owner"


def test_an_owner_may_not_demote_a_fellow_owner(client: TestClient) -> None:
    """Owners hold the project jointly, so neither can unseat the other."""
    project_id = _create_project(client=client, caller="bob", name="bobs project")
    _grant(
        client=client,
        project_id=project_id,
        caller="bob",
        email="alice@example.com",
        role="owner",
    )

    response = _grant(
        client=client,
        project_id=project_id,
        caller="bob",
        email="alice@example.com",
        role="admin",
    )

    assert response.status_code == httpx.codes.FORBIDDEN, response.text
    assert "cannot be taken away once it is granted" in response.json()["reason"]


def test_an_owner_may_not_demote_themselves_either(client: TestClient) -> None:
    """Stepping down is a demotion of an owner like any other."""
    project_id = _create_project(client=client, caller="bob", name="bobs project")

    response = _grant(
        client=client,
        project_id=project_id,
        caller="bob",
        email="bob@example.com",
        role="viewer",
    )

    assert response.status_code == httpx.codes.FORBIDDEN, response.text


def test_an_admin_may_not_demote_an_owner(client: TestClient) -> None:
    """What an owner may not do to an owner, an admin may not do either."""
    project_id = _create_project(client=client, caller="bob", name="bobs project")
    _grant(
        client=client,
        project_id=project_id,
        caller="bob",
        email="alice@example.com",
        role="admin",
    )

    response = _grant(
        client=client,
        project_id=project_id,
        caller="alice",
        email="bob@example.com",
        role="viewer",
    )

    assert response.status_code == httpx.codes.FORBIDDEN, response.text


def test_a_platform_administrator_may_hand_a_project_on(
    client: TestClient, session: Session
) -> None:
    """Somebody has to be able to move a project whose owner has gone.

    The rules above are about who inside a project may rearrange it. A
    platform administrator is outside it, and is the one route left when the
    only person who could have granted the role is no longer there to.
    """
    make_platform_admin(session=session, email="root@example.com")
    project_id = _create_project(client=client, caller="bob", name="bobs project")

    promoted = _grant(
        client=client,
        project_id=project_id,
        caller="root",
        email="alice@example.com",
        role="owner",
    )
    assert promoted.status_code == httpx.codes.OK, promoted.text

    demoted = _grant(
        client=client,
        project_id=project_id,
        caller="root",
        email="bob@example.com",
        role="viewer",
    )
    assert demoted.status_code == httpx.codes.OK, demoted.text
    assert demoted.json()["role"] == "viewer"


def test_a_refusal_does_not_reveal_which_addresses_exist(client: TestClient) -> None:
    """An outsider learns they are an outsider, and nothing about the users.

    The member being granted a role has to be looked up before the decision
    can be made, so the answer is checked here to be the refusal rather than
    the lookup's failure.
    """
    project_id = _create_project(client=client, caller="bob", name="bobs project")

    unknown = _grant(
        client=client,
        project_id=project_id,
        caller="alice",
        email="nobody@example.com",
        role="viewer",
    )
    known = _grant(
        client=client,
        project_id=project_id,
        caller="alice",
        email="root@example.com",
        role="viewer",
    )

    assert unknown.status_code == httpx.codes.FORBIDDEN, unknown.text
    assert known.status_code == unknown.status_code


# --- who is in a project ----------------------------------------------------


def test_the_member_list_names_everybody_and_the_role_they_hold(
    client: TestClient,
) -> None:
    """The creator is in it as owner, alongside whoever they have let in."""
    project_id = _create_project(client=client, caller="bob", name="bobs project")
    _grant(
        client=client,
        project_id=project_id,
        caller="bob",
        email="alice@example.com",
        role="viewer",
    )

    response = client.get(
        f"/projects/{project_id}/members", headers=headers_for(caller="bob")
    )

    assert response.status_code == httpx.codes.OK, response.text
    assert {(entry["email"], entry["role"]) for entry in response.json()} == {
        ("bob@example.com", "owner"),
        ("alice@example.com", "viewer"),
    }


def test_a_viewer_may_see_who_else_is_in_the_project(client: TestClient) -> None:
    """Reading the membership is reading the project, not administering it."""
    project_id = _create_project(client=client, caller="bob", name="bobs project")
    _grant(
        client=client,
        project_id=project_id,
        caller="bob",
        email="alice@example.com",
        role="viewer",
    )

    response = client.get(
        f"/projects/{project_id}/members", headers=headers_for(caller="alice")
    )

    assert response.status_code == httpx.codes.OK, response.text
    assert len(response.json()) == 2


def test_an_outsider_cannot_see_who_is_in_a_project(client: TestClient) -> None:
    """Who works on what is as much the project's business as its contents."""
    project_id = _create_project(client=client, caller="bob", name="bobs project")

    response = client.get(
        f"/projects/{project_id}/members", headers=headers_for(caller="alice")
    )

    assert response.status_code == httpx.codes.FORBIDDEN, response.text


def test_the_member_list_of_a_project_that_does_not_exist_is_a_404(
    client: TestClient,
) -> None:
    """Asked about nothing, the platform says so rather than answering empty."""
    response = client.get(
        f"/projects/{uuid4()}/members", headers=headers_for(caller="alice")
    )

    assert response.status_code == httpx.codes.NOT_FOUND, response.text
