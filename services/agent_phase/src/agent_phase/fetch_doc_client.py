"""Invokes the real `fetch_doc` Lambda (a separate deployable, per the
design artifact's diagram: `agent_phase -> AgentCore Gateway -> λ
fetch_doc`) rather than importing `fetch_doc`'s package in-process.

Why a real cross-Lambda call instead of a direct import, even though both
are Python and could share a process: `fetch_doc` has zero AWS
permissions as a hard invariant (CLAUDE.md's permissions table) --
keeping it a genuinely separate execution context is what makes that
invariant meaningful rather than aspirational. `agent_phase`'s own IAM
role gets exactly one addition for this: `lambda:InvokeFunction` scoped
to `fetch_doc`'s ARN (task 3.3-tf), nothing broader.

AgentCore Gateway itself (Cedar-based tool policy, per the artifact) is
listed in PLAN.md's Plus section, not built in this pass -- this direct
Lambda invocation is the prototype's stand-in for that hop, with the same
resource-scoped IAM boundary already enforced by ordinary least-privilege
policy, not by Cedar.
"""

from __future__ import annotations

import json
from typing import Any, Protocol


class FetchDocInvocationError(Exception):
    """The fetch_doc Lambda invocation itself failed or the function
    raised (disallowed host, oversized response, network error, ...).
    The message is the function's own error, not a generic wrapper --
    agent_phase.tools.fetch_doc surfaces it to the model as a tool error
    so it can adjust rather than retrying the same rejected URL."""


class SupportsInvoke(Protocol):
    def invoke(self, *, FunctionName: str, Payload: bytes) -> dict[str, Any]: ...


def make_fetch_doc_fn(lambda_client: SupportsInvoke, function_name: str):
    """Returns a `FetchDocFn` (str -> str) bound to one Lambda client and
    function name, for `agent_builder.build_agent`'s `fetch_doc_fn`
    parameter."""

    def fetch_doc(url: str) -> str:
        response = lambda_client.invoke(
            FunctionName=function_name,
            Payload=json.dumps({"url": url}).encode("utf-8"),
        )
        payload = json.loads(response["Payload"].read())

        if response.get("FunctionError"):
            message = payload.get("errorMessage", str(payload))
            raise FetchDocInvocationError(message)

        return payload["content"]

    return fetch_doc
