"""Adapter that lets the agent call the fetch_doc Lambda for allowlisted documentation."""

from __future__ import annotations

import json
from typing import Any, Protocol


class FetchDocInvocationError(Exception):
    pass


class SupportsInvoke(Protocol):
    def invoke(self, *, FunctionName: str, Payload: bytes) -> dict[str, Any]: ...


def make_fetch_doc_fn(lambda_client: SupportsInvoke, function_name: str):
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
