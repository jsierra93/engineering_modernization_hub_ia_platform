"""Fase 4 (4.4): the objective -> strategy resolver, the one place
services/api calls Bedrock. Uses a fake bedrock_client (no moto support
for bedrock-runtime's invoke_model) that returns a canned
Anthropic-on-Bedrock response shape."""

from __future__ import annotations

import io
import json

import pytest
from core_py.models import StrategyLimit, StrategyLimits, StrategyManifest

from api.resolver import NoStrategyMatchError, resolve_strategy

_CANDIDATES = [
    StrategyManifest(
        id="python-pydantic-v2",
        version="1.0.0",
        title="Pydantic v1 -> v2",
        limits=StrategyLimits(
            max_usd=StrategyLimit(default=2.0, max=5.0),
            max_iterations=StrategyLimit(default=3, max=5),
            max_minutes=StrategyLimit(default=20, max=45),
        ),
        checks=["install"],
        writable_paths=["**/*.py"],
        sources=["https://example.com"],
    )
]


class _FakeBedrockClient:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.last_call = None

    def invoke_model(self, **kwargs):
        self.last_call = kwargs
        body = json.dumps({"content": [{"text": self._response_text}]}).encode("utf-8")
        return {"body": io.BytesIO(body)}


def test_resolve_strategy_returns_matching_manifest_and_confidence():
    client = _FakeBedrockClient(json.dumps({"strategy_id": "python-pydantic-v2", "confidence": 0.92}))

    manifest, confidence = resolve_strategy("migrar de pydantic v1 a v2", _CANDIDATES, bedrock_client=client)

    assert manifest.id == "python-pydantic-v2"
    assert confidence == pytest.approx(0.92)
    assert client.last_call["modelId"]


def test_resolve_strategy_raises_when_model_returns_null():
    client = _FakeBedrockClient(json.dumps({"strategy_id": None, "confidence": 0.0}))

    with pytest.raises(NoStrategyMatchError):
        resolve_strategy("pintar la casa", _CANDIDATES, bedrock_client=client)


def test_resolve_strategy_raises_on_hallucinated_id_outside_candidates():
    """A model returning an id NOT in the candidate list is treated as no
    match -- never trusted at face value."""
    client = _FakeBedrockClient(json.dumps({"strategy_id": "made-up-strategy", "confidence": 0.99}))

    with pytest.raises(NoStrategyMatchError):
        resolve_strategy("migrar de pydantic v1 a v2", _CANDIDATES, bedrock_client=client)


def test_resolve_strategy_raises_on_non_json_response():
    client = _FakeBedrockClient("not json at all")

    with pytest.raises(NoStrategyMatchError):
        resolve_strategy("migrar de pydantic v1 a v2", _CANDIDATES, bedrock_client=client)


def test_resolve_strategy_raises_when_no_candidates_registered():
    client = _FakeBedrockClient(json.dumps({"strategy_id": None, "confidence": 0.0}))

    with pytest.raises(NoStrategyMatchError):
        resolve_strategy("cualquier cosa", [], bedrock_client=client)
