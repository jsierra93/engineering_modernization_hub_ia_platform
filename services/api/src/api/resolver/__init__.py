"""The only Bedrock call outside the LLM zone: maps a free-text objective to a registered strategy id.
The model picks from a closed candidate list; anything else is treated as no match.
"""

from __future__ import annotations

import json
import os
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from core_py.bedrock_models import ModelRole, resolve_model_id
from core_py.observability import log_event
from core_py.models import StrategyManifest

_SYSTEM_PROMPT = (
    "You match a free-text software-modernization objective to exactly "
    "one strategy id from a fixed candidate list, or to none if none "
    "genuinely fit. Respond with ONLY a JSON object of the exact shape "
    '{"strategy_id": <id-from-the-list-or-null>, "confidence": <0.0-1.0>} '
    "-- no prose, no markdown fencing. Never return an id that is not in "
    "the candidate list."
)


MIN_CONFIDENCE_ENV = "MODHUB_RESOLVER_MIN_CONFIDENCE"
DEFAULT_MIN_CONFIDENCE = 0.6


class NoStrategyMatchError(Exception):
    pass


class ResolverUnavailableError(Exception):
    pass


def _client(bedrock_client: Any) -> Any:
    if bedrock_client is not None:
        return bedrock_client
    import boto3

    return boto3.client("bedrock-runtime")


def _strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    return body.rsplit("```", 1)[0].strip()


def resolve_strategy(
    objetivo: str,
    candidates: list[StrategyManifest],
    *,
    bedrock_client: Any = None,
    model_id: str | None = None,
) -> tuple[StrategyManifest, float]:
    if not candidates:
        raise NoStrategyMatchError("no strategies are registered")

    resolved_model_id = resolve_model_id(ModelRole.ANALYSIS, override=model_id)
    by_id = {manifest.id: manifest for manifest in candidates}
    catalog = [{"id": manifest.id, "title": manifest.title} for manifest in candidates]

    user_message = json.dumps({"objetivo": objetivo, "candidates": catalog})

    try:
        response = _client(bedrock_client).invoke_model(
            modelId=resolved_model_id,
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 256,
                    "temperature": 0,
                    "system": _SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_message}],
                }
            ),
        )
        payload = json.loads(response["body"].read())
        text = payload["content"][0]["text"]
    except (ClientError, BotoCoreError) as exc:
        log_event("resolver.unavailable", model_id=resolved_model_id, error=str(exc)[:300])
        raise ResolverUnavailableError(str(exc)) from exc

    try:
        parsed = json.loads(_strip_markdown_fence(text))
    except json.JSONDecodeError as exc:
        log_event("resolver.unparseable_response", model_id=resolved_model_id, raw=text[:500])
        raise NoStrategyMatchError(f"model response was not valid JSON: {text!r}") from exc

    if not isinstance(parsed, dict):
        log_event("resolver.unparseable_response", model_id=resolved_model_id, raw=text[:500])
        raise NoStrategyMatchError(f"model response was not a JSON object: {text!r}")

    strategy_id = parsed.get("strategy_id")
    try:
        confidence = float(parsed.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    if not strategy_id or strategy_id not in by_id:
        log_event(
            "resolver.no_match",
            model_id=resolved_model_id,
            returned_id=strategy_id,
            confidence=confidence,
            candidates=[m.id for m in candidates],
        )
        raise NoStrategyMatchError(f"objetivo did not match a registered strategy: {objetivo!r}")

    minimum = float(os.environ.get(MIN_CONFIDENCE_ENV, DEFAULT_MIN_CONFIDENCE))
    if confidence < minimum:
        log_event(
            "resolver.low_confidence",
            model_id=resolved_model_id,
            returned_id=strategy_id,
            confidence=confidence,
            minimum=minimum,
        )
        raise NoStrategyMatchError(
            f"matched {strategy_id!r} with confidence {confidence} below the {minimum} minimum"
        )

    log_event("resolver.matched", model_id=resolved_model_id, strategy_id=strategy_id, confidence=confidence)
    return by_id[strategy_id], confidence
