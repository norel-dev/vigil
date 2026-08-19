"""Tests of what happens between a decision and the action it guards.

These tests use hand written decision points rather than a policy engine, so
that failures which are hard to arrange against a healthy OPA — an unreachable
server, a rule that answers nonsense — can be exercised directly.
"""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from src.app import create_app
from src.authz.enforcement import AccessEnforcer
from src.authz.policy import (
    Action,
    AuthorizationRequest,
    Decision,
    Resource,
    ResourceType,
    Subject,
)
from src.database.engine import create_database_engine
from src.database.migrations import upgrade_to_head
from src.features.users.model import User
from src.identity.keys import digest_of
from src.identity.model import ApiKey
from src.platform.config import AppConfig, AuthConfig, DatabaseConfig, OpaConfig
from src.platform.exceptions import PermissionDeniedError, PolicyDecisionPointError
from tests.conftest import api_key_for, headers_for


class ScriptedDecisionPoint:
    """A decision point that answers with whatever it was handed."""

    def __init__(self, *, decision: Decision) -> None:
        """Bind the decision point to its answer.

        Args:
            decision: The answer to give to every question.
        """
        self._decision = decision
        self.questions: list[AuthorizationRequest] = []

    async def decide(self, *, request: AuthorizationRequest) -> Decision:
        """Record the question and return the scripted answer.

        Args:
            request: The question being asked.

        Returns:
            Decision: The scripted answer.
        """
        self.questions.append(request)
        return self._decision

    async def filter_allowed(self, **_: object) -> set[str]:
        """Return nothing; this stub is only used for single decisions.

        Returns:
            set[str]: Always empty.
        """
        return set()


class BrokenDecisionPoint:
    """A decision point that cannot answer at all."""

    async def decide(self, **_: object) -> Decision:
        """Fail the way an unreachable OPA does.

        Raises:
            PolicyDecisionPointError: Always.
        """
        raise PolicyDecisionPointError("OPA is down")

    async def filter_allowed(self, **_: object) -> set[str]:
        """Fail the way an unreachable OPA does.

        Raises:
            PolicyDecisionPointError: Always.
        """
        raise PolicyDecisionPointError("OPA is down")


def _subject() -> Subject:
    """Return an arbitrary subject to ask questions about.

    Returns:
        Subject: A caller with no roles anywhere.
    """
    return Subject(id=uuid4(), email="alice@example.com")


def _resource() -> Resource:
    """Return an arbitrary datastore to ask questions about.

    Returns:
        Resource: A datastore, which lives at the system level.
    """
    return Resource(type=ResourceType.DATASTORE, id="my store")


async def test_an_allowed_action_passes_through() -> None:
    """A decision of `allow` lets the caller proceed."""
    enforcer = AccessEnforcer(
        decision_point=ScriptedDecisionPoint(decision=Decision(allow=True, reason="allowed")),
        resource_filter=BrokenDecisionPoint(),
    )

    await enforcer.ensure_allowed(
        subject=_subject(), action=Action.DATASTORE_QUERY, resource=_resource()
    )


async def test_a_denied_action_raises_with_the_policys_reason() -> None:
    """The explanation the policy gave survives all the way to the caller."""
    enforcer = AccessEnforcer(
        decision_point=ScriptedDecisionPoint(
            decision=Decision(allow=False, reason="not a member of the project")
        ),
        resource_filter=BrokenDecisionPoint(),
    )

    with pytest.raises(PermissionDeniedError) as raised:
        await enforcer.ensure_allowed(
            subject=_subject(), action=Action.DATASTORE_QUERY, resource=_resource()
        )

    assert raised.value.reason == "not a member of the project"
    assert raised.value.action == "datastore.query"


async def test_an_unreachable_policy_engine_never_allows_the_action() -> None:
    """A decision point that cannot answer denies rather than defaults to yes."""
    enforcer = AccessEnforcer(
        decision_point=BrokenDecisionPoint(), resource_filter=BrokenDecisionPoint()
    )

    with pytest.raises(PolicyDecisionPointError):
        await enforcer.ensure_allowed(
            subject=_subject(), action=Action.DATASTORE_QUERY, resource=_resource()
        )


async def test_an_unreachable_policy_engine_never_lists_anything() -> None:
    """The same holds for listings: no decision means no rows."""
    enforcer = AccessEnforcer(
        decision_point=BrokenDecisionPoint(), resource_filter=BrokenDecisionPoint()
    )

    with pytest.raises(PolicyDecisionPointError):
        await enforcer.keep_allowed(
            subject=_subject(), action=Action.DATASTORE_READ, resources=[_resource()]
        )


async def test_the_question_carries_the_subjects_roles() -> None:
    """The policy is given the caller's memberships, and does not look them up."""
    decision_point = ScriptedDecisionPoint(decision=Decision(allow=True))
    enforcer = AccessEnforcer(
        decision_point=decision_point, resource_filter=BrokenDecisionPoint()
    )
    subject = _subject()

    await enforcer.ensure_allowed(
        subject=subject, action=Action.DATASTORE_READ, resource=_resource()
    )

    asked = decision_point.questions[0]
    assert asked.subject == subject
    assert asked.action is Action.DATASTORE_READ


# --- and how a failure reaches the caller -----------------------------------
#
# The tests above stop at the exception. These carry it the rest of the way,
# through a real application whose policy engine is not there, because the
# status code is the part an operator will actually see: a 503 says the
# platform could not decide, where a 500 would say it broke and a 403 would
# say the caller was refused. Only one of those is true, and only one of them
# is safe to retry.


@pytest.fixture
def client_without_a_policy_engine(tmp_path: Path) -> Iterator[TestClient]:
    """Build the real application, pointed at an OPA that is not running.

    Args:
        tmp_path: Directory unique to the running test.

    Yields:
        TestClient: A client whose every guarded request has to fail.
    """
    config = AppConfig(
        database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'test.db'}", echo=False),
        auth=AuthConfig(),
        opa=OpaConfig(url="http://127.0.0.1:1", request_timeout_seconds=0.25),
    )
    engine = create_database_engine(config=config.database)
    upgrade_to_head(engine=engine)
    with Session(engine) as session:
        user = User(email="alice@example.com", name="Alice")
        session.add(user)
        session.add(
            ApiKey(
                user_id=user.id,
                name="test",
                secret_hash=digest_of(key=api_key_for(caller="alice")),
            )
        )
        session.commit()

    with TestClient(create_app(config=config)) as client:
        yield client

    engine.dispose()


def test_an_action_needing_a_decision_is_answered_with_503(
    client_without_a_policy_engine: TestClient,
) -> None:
    """Could not decide, rather than refused or broken."""
    response = client_without_a_policy_engine.post(
        "/datastores/",
        json={
            "name": "warehouse",
            "description": None,
            "datastore": {
                "implementation": "sqlite",
                "sqlite_connection_string": "/tmp/unused.db",
            },
        },
        headers=headers_for(caller="alice"),
    )

    assert response.status_code == httpx.codes.SERVICE_UNAVAILABLE, response.text
    assert "policy" in response.json()["detail"].lower()


def test_nothing_is_done_when_the_decision_could_not_be_made(
    client_without_a_policy_engine: TestClient,
) -> None:
    """The action is refused on the way in, so it leaves nothing behind.

    Creating a project needs no decision - any user may - which is what makes
    it usable here: it gives Alice something that is provably hers to read,
    and reading it is what needs the policy.
    """
    created = client_without_a_policy_engine.post(
        "/projects/",
        json={"name": "a project", "description": None},
        headers=headers_for(caller="alice"),
    )
    assert created.status_code == httpx.codes.CREATED, created.text

    read_back = client_without_a_policy_engine.get(
        f"/projects/{created.json()['id']}", headers=headers_for(caller="alice")
    )

    assert read_back.status_code == httpx.codes.SERVICE_UNAVAILABLE, read_back.text


def test_a_listing_is_not_quietly_emptied_when_nothing_can_decide(
    client_without_a_policy_engine: TestClient,
) -> None:
    """A filtered listing fails loudly rather than answering "you may see nothing".

    This is the failure most likely to go unnoticed, because an empty page
    looks like an ordinary answer to whoever is reading it. Alice's own
    project has to exist first: filtering nothing asks the policy nothing, so
    an empty platform would answer an empty list quite correctly.
    """
    created = client_without_a_policy_engine.post(
        "/projects/",
        json={"name": "a project", "description": None},
        headers=headers_for(caller="alice"),
    )
    assert created.status_code == httpx.codes.CREATED, created.text

    response = client_without_a_policy_engine.get(
        "/projects/", headers=headers_for(caller="alice")
    )

    assert response.status_code == httpx.codes.SERVICE_UNAVAILABLE, response.text


def test_authentication_still_happens_before_any_decision_is_needed(
    client_without_a_policy_engine: TestClient,
) -> None:
    """An unknown caller is refused outright, policy engine or no policy engine.

    Who you are is settled by the platform's own records, so an outage in the
    decision point must not turn a bad credential into a retryable 503.
    """
    response = client_without_a_policy_engine.get(
        "/projects/", headers={"Authorization": "Bearer dpk_not_a_key_this_platform_issued"}
    )

    assert response.status_code == httpx.codes.UNAUTHORIZED, response.text


def test_the_health_endpoint_still_answers(
    client_without_a_policy_engine: TestClient,
) -> None:
    """Health is what a load balancer asks, and it does not depend on OPA.

    Reporting the process as down because OPA is would take the API out of
    the load balancer for a fault it can still describe perfectly well.
    """
    assert client_without_a_policy_engine.get("/").status_code == httpx.codes.OK
