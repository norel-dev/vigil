"""An Open Policy Agent backed policy decision point.

The API asks OPA the questions; the answers live in the Rego policy under
`policies/`. Nothing about the permission model is encoded here, which is the
point: changing who may query which datastore is a policy change, not a code
change.
"""

import httpx
from loguru import logger
from pydantic import ValidationError

from src.authz.policy import (
    Action,
    AuthorizationRequest,
    Decision,
    Resource,
    Subject,
)
from src.platform.config import OpaConfig
from src.platform.exceptions import PolicyDecisionPointError

__all__ = ["OpaPolicyDecisionPoint"]


class OpaPolicyDecisionPoint:
    """Renders decisions by calling OPA's Data API over HTTP.

    Implements both `PolicyDecisionPoint` and `ResourceFilter`.
    """

    def __init__(self, *, config: OpaConfig, client: httpx.AsyncClient) -> None:
        """Bind the decision point to an OPA server.

        Args:
            config: Where OPA lives and which rules to query.
            client: The HTTP client used for every request. The caller owns
                its lifetime.
        """
        self._config = config
        self._client = client

    async def decide(self, *, request: AuthorizationRequest) -> Decision:
        """Ask OPA whether `request` is allowed.

        Args:
            request: The question to answer.

        Returns:
            Decision: Whether the action is allowed, and why.

        Raises:
            PolicyDecisionPointError: If OPA could not be reached, answered
                with an error, or returned something that is not a decision.
        """
        result = await self._query(
            path=self._config.decision_path,
            document=request.model_dump(mode="json"),
        )

        try:
            return Decision.model_validate(result)
        except ValidationError as error:
            raise PolicyDecisionPointError(
                f"OPA rule '{self._config.decision_path}' did not return a "
                f"decision: {error}"
            ) from error

    async def filter_allowed(
        self,
        *,
        subject: Subject,
        action: Action,
        resources: list[Resource],
    ) -> set[str]:
        """Ask OPA which of `resources` the subject may act on.

        Answering in a single round trip keeps listing endpoints from making
        one policy call per row.

        Args:
            subject: The caller the resources are filtered for.
            action: The action the caller wants to perform on them.
            resources: The candidate resources.

        Returns:
            set[str]: The ids of the allowed subset of `resources`.

        Raises:
            PolicyDecisionPointError: If OPA could not be reached, answered
                with an error, or returned something that is not a list of ids.
        """
        if not resources:
            return set()

        result = await self._query(
            path=self._config.filter_path,
            document={
                "subject": subject.model_dump(mode="json"),
                "action": action.value,
                "resources": [resource.model_dump(mode="json") for resource in resources],
            },
        )

        if not isinstance(result, list):
            raise PolicyDecisionPointError(
                f"OPA rule '{self._config.filter_path}' did not return a list "
                f"of resource ids, but {type(result).__name__}"
            )

        allowed_ids = [entry for entry in result if isinstance(entry, str)]
        if len(allowed_ids) != len(result):
            raise PolicyDecisionPointError(
                f"OPA rule '{self._config.filter_path}' returned resource ids "
                "that are not strings"
            )

        return set(allowed_ids)

    async def _query(self, *, path: str, document: object) -> object:
        """Evaluate the rule at `path` against `document`.

        Args:
            path: Data API path of the rule, without the leading '/v1/data/'.
            document: The value to send as OPA's `input`.

        Returns:
            object: The rule's result, exactly as OPA rendered it.

        Raises:
            PolicyDecisionPointError: If OPA is unreachable, returns a non
                success status, answers with a body that is not JSON, or
                leaves the rule undefined.
        """
        url = f"{self._config.url.rstrip('/')}/v1/data/{path.strip('/')}"

        try:
            response = await self._client.post(
                url,
                json={"input": document},
                timeout=self._config.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as error:
            raise PolicyDecisionPointError(f"Could not reach OPA at {url}: {error}") from error
        except ValueError as error:
            raise PolicyDecisionPointError(
                f"OPA at {url} returned invalid JSON: {error}"
            ) from error

        if not isinstance(payload, dict) or "result" not in payload:
            raise PolicyDecisionPointError(
                f"OPA rule '{path}' is undefined. The policy is most likely "
                "not loaded into the server."
            )

        return payload["result"]

    async def check_reachable(self) -> bool:
        """Report whether OPA answers, so startup can warn about a bad setup.

        Returns:
            bool: True if OPA responded to a health check.
        """
        url = f"{self._config.url.rstrip('/')}/health"
        try:
            response = await self._client.get(
                url, timeout=self._config.request_timeout_seconds
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            logger.warning("Open Policy Agent at {} is not reachable: {}", url, error)
            return False

        return True
