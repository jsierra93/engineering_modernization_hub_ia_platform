"""Task 3.3/3.6 integration point: agent_phase invokes fetch_doc as a real
separate Lambda, matching the design artifact's diagram. No real AWS --
a fake Lambda client stands in, matching fetch_doc's actual return shape
exactly (see services/fetch_doc/src/fetch_doc/handler.py's handler())."""

from __future__ import annotations

import json

import pytest

from agent_phase.fetch_doc_client import FetchDocInvocationError, make_fetch_doc_fn


class _FakePayload:
    def __init__(self, data: dict):
        self._data = json.dumps(data).encode()

    def read(self):
        return self._data


class _FakeLambdaClient:
    def __init__(self, response: dict):
        self.response = response
        self.calls: list[tuple[str, dict]] = []

    def invoke(self, *, FunctionName, Payload):
        self.calls.append((FunctionName, json.loads(Payload)))
        return self.response


def test_successful_fetch_returns_the_content_string():
    client = _FakeLambdaClient(
        {"Payload": _FakePayload({"url": "https://docs.pydantic.dev/x", "host": "docs.pydantic.dev", "content": "the migration guide text", "content_type": "text/html"})}
    )
    fetch_doc = make_fetch_doc_fn(client, function_name="modhub-fetch-doc")

    result = fetch_doc("https://docs.pydantic.dev/x")

    assert result == "the migration guide text"
    assert client.calls == [("modhub-fetch-doc", {"url": "https://docs.pydantic.dev/x"})]


def test_function_error_is_raised_as_fetch_doc_invocation_error_with_the_real_message():
    client = _FakeLambdaClient(
        {
            "FunctionError": "Unhandled",
            "Payload": _FakePayload({"errorMessage": "rejected 'https://evil.com/x': host 'evil.com' is not on the allowlist"}),
        }
    )
    fetch_doc = make_fetch_doc_fn(client, function_name="modhub-fetch-doc")

    with pytest.raises(FetchDocInvocationError, match="not on the allowlist"):
        fetch_doc("https://evil.com/x")
