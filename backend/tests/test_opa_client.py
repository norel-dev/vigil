"""Tests of the conversation with the Open Policy Agent server.

The policy itself is tested by `opa test policies`; what is checked here is
that a misbehaving server can never turn into an allowed action.
"""

from typing import Any
from uuid import uuid4

import httpx
import pytest

from src.authz.opa import OpaPolicyDecisionPoint
from src.authz.policy import (
    Action,
    AuthorizationRequest,
    Resource,
    ResourceType,
    Subject,
)
from src.platform.config import OpaConfig
from src.platform.exceptions import PolicyDecisionPointError


def _decision_point(*, handler: Any) -> OpaPolicyDecisionPoint:
    """Build a decision point whose OPA is `handler`.

    Args:
        handler: Function answering the requests the client makes.

    Returns:
        OpaPolicyDecisionPoint: A decision point talking to the mock transport.
    """
    return OpaPolicyDecisionPoint(
        config=OpaConfig(url="http://opa.invalid"),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _request() -> AuthorizationRequest:
    """Return an arbitrary question to ask.

    Returns:
        AuthorizationRequest: A question about querying a datastore.
    """
    return AuthorizationRequest(
        subject=Subject(id=uuid4(), email="alice@example.com"),
        action=Action.DATASTORE_QUERY,
        resource=Resource(type=ResourceType.DATASTORE, id="my store"),
    )


async def _filter_one(*, handler: Any) -> set[str]:
    """Ask a decision point backed by `handler` to filter one resource.

    Args:
        handler: Function answering the requests the client makes.

    Returns:
        set[str]: The ids the policy allowed.
    """
    return await _decision_point(handler=handler).filter_allowed(
        subject=Subject(id=uuid4(), email="alice@example.com"),
        action=Action.DATASTORE_READ,
        resources=[Resource(type=ResourceType.DATASTORE, id="my store")],
    )


async def test_a_decision_is_read_from_the_result_document() -> None:
    """OPA's answer is unwrapped into a decision."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            httpx.codes.OK, json={"result": {"allow": True, "reason": "allowed"}}
        )

    decision = await _decision_point(handler=handler).decide(request=_request())

    assert decision.allow is True
    assert decision.reason == "allowed"


async def test_the_question_is_sent_as_opas_input_document() -> None:
    """The subject, action and resource travel to OPA as `input`.

    The resource's scope has to be among them: it is what tells the policy
    whether to judge the object by platform administration or by project
    membership, and the policy has no other way to find out.
    """
    sent: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(httpx.Response(200, content=request.content).json())
        return httpx.Response(httpx.codes.OK, json={"result": {"allow": False, "reason": "no"}})

    question = _request()
    await _decision_point(handler=handler).decide(request=question)

    assert sent["input"]["action"] == "datastore.query"
    assert sent["input"]["subject"]["email"] == "alice@example.com"
    assert sent["input"]["resource"]["id"] == "my store"
    assert sent["input"]["resource"]["scope"] == "system"


async def test_an_unreachable_server_fails_rather_than_allows() -> None:
    """A network failure surfaces as an error, never as a decision."""

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(PolicyDecisionPointError, match="Could not reach OPA"):
        await _decision_point(handler=handler).decide(request=_request())


async def test_an_unloaded_policy_fails_rather_than_allows() -> None:
    """An OPA with no policy loaded leaves the rule undefined, which is an error.

    This is the dangerous case: OPA answers 200 with an empty document, and
    reading a missing `allow` as `false` would be right, but reading a missing
    `result` as anything other than a failure would be very wrong.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(httpx.codes.OK, json={})

    with pytest.raises(PolicyDecisionPointError, match="undefined"):
        await _decision_point(handler=handler).decide(request=_request())


async def test_a_server_error_fails_rather_than_allows() -> None:
    """A 500 from OPA is not an answer."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(httpx.codes.INTERNAL_SERVER_ERROR, json={"error": "boom"})

    with pytest.raises(PolicyDecisionPointError):
        await _decision_point(handler=handler).decide(request=_request())


async def test_a_nonsense_answer_fails_rather_than_allows() -> None:
    """A rule that returns something other than a decision is an error."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(httpx.codes.OK, json={"result": "yes please"})

    with pytest.raises(PolicyDecisionPointError, match="did not return a decision"):
        await _decision_point(handler=handler).decide(request=_request())


async def test_filtering_an_empty_list_asks_opa_nothing() -> None:
    """Listing an empty table does not need a round trip."""

    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("OPA should not have been called")

    allowed = await _decision_point(handler=handler).filter_allowed(
        subject=Subject(id=uuid4(), email="alice@example.com"),
        action=Action.DATASTORE_READ,
        resources=[],
    )

    assert allowed == set()


async def test_filtering_returns_the_allowed_ids() -> None:
    """The filter rule's answer becomes the set of ids the caller may see."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(httpx.codes.OK, json={"result": ["my store"]})

    allowed = await _decision_point(handler=handler).filter_allowed(
        subject=Subject(id=uuid4(), email="alice@example.com"),
        action=Action.DATASTORE_READ,
        resources=[Resource(type=ResourceType.DATASTORE, id="my store")],
    )

    assert allowed == {"my store"}


async def test_a_filter_answer_that_is_not_a_list_fails_rather_than_allows() -> None:
    """A rule that answers with the wrong shape has to be treated as broken.

    The tempting reading of a non-list is "nothing was allowed", which would
    hide a policy bug behind an empty page instead of reporting it.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(httpx.codes.OK, json={"result": {"my store": True}})

    with pytest.raises(PolicyDecisionPointError, match="did not return a list"):
        await _filter_one(handler=handler)


async def test_a_filter_answer_holding_something_that_is_not_an_id_fails() -> None:
    """Ids the platform cannot match are refused rather than quietly dropped."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(httpx.codes.OK, json={"result": ["my store", 7]})

    with pytest.raises(PolicyDecisionPointError, match="not strings"):
        await _filter_one(handler=handler)


async def test_an_unreachable_server_fails_the_filter_rather_than_emptying_it() -> None:
    """The same rule as for a single decision: no answer is not a "no"."""

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(PolicyDecisionPointError, match="Could not reach OPA"):
        await _filter_one(handler=handler)


async def test_ids_the_policy_did_not_return_are_left_out() -> None:
    """Filtering is what turns a listing into the part the caller may see."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(httpx.codes.OK, json={"result": ["mine"]})

    allowed = await _decision_point(handler=handler).filter_allowed(
        subject=Subject(id=uuid4(), email="alice@example.com"),
        action=Action.DATASTORE_READ,
        resources=[
            Resource(type=ResourceType.DATASTORE, id="mine"),
            Resource(type=ResourceType.DATASTORE, id="somebody elses"),
        ],
    )

    assert allowed == {"mine"}


# --- the startup health check -----------------------------------------------


async def test_a_server_that_answers_is_reported_reachable() -> None:
    """This is what lets startup log a working setup rather than guess at one."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(httpx.codes.OK, json={})

    assert await _decision_point(handler=handler).check_reachable() is True


async def test_a_server_that_does_not_answer_is_reported_unreachable() -> None:
    """Startup warns and carries on; the refusal comes later, per request.

    Failing to start would be worse: OPA coming up a moment after the API is
    an ordinary thing for two containers to do.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    assert await _decision_point(handler=handler).check_reachable() is False


async def test_a_server_answering_with_an_error_is_reported_unreachable() -> None:
    """Reachable is about being usable, not about the socket being open."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(httpx.codes.INTERNAL_SERVER_ERROR)

    assert await _decision_point(handler=handler).check_reachable() is False


async def test_an_answer_that_is_not_json_fails_rather_than_allows() -> None:
    """Something is answering on OPA's port, but it is not OPA.

    A proxy's error page or a captive portal is the usual cause, and it
    arrives with a perfectly good status code, so the body is what gives it
    away.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(httpx.codes.OK, text="<html>not the policy engine</html>")

    with pytest.raises(PolicyDecisionPointError, match="invalid JSON"):
        await _decision_point(handler=handler).decide(request=_request())
