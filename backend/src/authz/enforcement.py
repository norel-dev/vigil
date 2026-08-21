"""Turning policy decisions into enforcement.

The decision point answers questions; this module is what acts on the answers.
Keeping the two apart means the endpoints never have to remember to check the
`allow` flag themselves, and that a decision point failure can only ever
result in access being refused.
"""

from loguru import logger

from src.authz.policy import (
    Action,
    AuthorizationRequest,
    MembershipChange,
    PolicyDecisionPoint,
    Resource,
    ResourceFilter,
    Subject,
)
from src.platform.exceptions import PermissionDeniedError

__all__ = ["AccessEnforcer"]


class AccessEnforcer:
    """Refuses actions the policy does not allow."""

    def __init__(
        self,
        *,
        decision_point: PolicyDecisionPoint,
        resource_filter: ResourceFilter,
    ) -> None:
        """Bind the enforcer to the policy engine it consults.

        Args:
            decision_point: Renders decisions for single requests.
            resource_filter: Narrows collections down to the allowed subset.
        """
        self._decision_point = decision_point
        self._resource_filter = resource_filter

    async def ensure_allowed(
        self,
        *,
        subject: Subject,
        action: Action,
        resource: Resource,
        membership_change: MembershipChange | None = None,
    ) -> None:
        """Return normally if the action is allowed, raise otherwise.

        Args:
            subject: The caller performing the action.
            action: The action being performed.
            resource: The object being acted on.
            membership_change: The role change being attempted, for an action
                that changes who belongs to a project. Left out otherwise,
                because no other question has one to describe.

        Raises:
            PermissionDeniedError: If the policy denied the action.
            PolicyDecisionPointError: If no decision could be rendered, in
                which case the action must not be performed either.
        """
        decision = await self._decision_point.decide(
            request=AuthorizationRequest(
                subject=subject,
                action=action,
                resource=resource,
                membership_change=membership_change,
            )
        )

        if decision.allow:
            return

        logger.info(
            "Denied {} on {} '{}' for {}: {}",
            action.value,
            resource.type.value,
            resource.id,
            subject.email,
            decision.reason,
        )
        raise PermissionDeniedError(
            action=action.value,
            resource=f"{resource.type.value} '{resource.id}'",
            reason=decision.reason or "the policy does not grant this action",
        )

    async def is_allowed(
        self,
        *,
        subject: Subject,
        action: Action,
        resource: Resource,
    ) -> bool:
        """Report whether the action is allowed, without refusing it.

        This exists for the one case where a denial is not the end of the
        request: choosing how much to permit rather than whether to permit
        anything. A caller who may not write to a table may still be allowed
        to read it, so the answer has to be usable rather than fatal.

        A decision point that cannot answer still raises, because "we could
        not tell" must never quietly become "no, so try something weaker".

        Args:
            subject: The caller performing the action.
            action: The action being considered.
            resource: The object being acted on.

        Returns:
            bool: True if the policy allows the action.

        Raises:
            PolicyDecisionPointError: If no decision could be rendered.
        """
        decision = await self._decision_point.decide(
            request=AuthorizationRequest(subject=subject, action=action, resource=resource)
        )
        return decision.allow

    async def keep_allowed(
        self,
        *,
        subject: Subject,
        action: Action,
        resources: list[Resource],
    ) -> set[str]:
        """Return the ids of the resources the subject may act on.

        Args:
            subject: The caller the resources are filtered for.
            action: The action the caller wants to perform on them.
            resources: The candidate resources.

        Returns:
            set[str]: The ids of the allowed subset of `resources`.

        Raises:
            PolicyDecisionPointError: If no decision could be rendered.
        """
        return await self._resource_filter.filter_allowed(
            subject=subject,
            action=action,
            resources=resources,
        )
