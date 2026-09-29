"""Who is calling: the identity API Gateway's JWT authorizer put on the request, and the ownership rule built on it.
Every service that answers "is this the requester?" asks here, so the rule exists once. The identity comes only from the
verified token: nothing the client writes in a header can stand in for it.
"""

from __future__ import annotations

import time
from typing import Any


def claims(event: dict[str, Any]) -> dict[str, Any]:
    return event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})


def caller_sub(event: dict[str, Any]) -> str | None:
    return claims(event).get("sub") or None


def is_owner(event: dict[str, Any], requested_by: str) -> bool:
    sub = caller_sub(event)
    return sub is not None and sub == requested_by


def auth_is_recent(event: dict[str, Any], max_age_seconds: int) -> bool:
    auth_time = claims(event).get("auth_time")
    if auth_time is None:
        return True
    return (time.time() - int(auth_time)) <= max_age_seconds
