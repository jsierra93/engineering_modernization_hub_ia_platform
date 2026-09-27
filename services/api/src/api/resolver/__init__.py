"""The ONLY Bedrock call outside the LLM zone: objetivo (free text) ->
strategy_id. CLAUDE.md's one documented exception to "the deterministic
core never calls a model" -- kept isolated in its own module so this
boundary stays as obvious in the code as it is in the design document.
`services/api` must never gain any other Bedrock use.

The model only ever picks from a closed candidate list it is given up
front; it never invents a strategy id. A hallucinated or missing id is
treated identically to an explicit "no match" -- both raise
NoStrategyMatchError, which create_run maps to 422 NO_STRATEGY_MATCH.
"""

from __future__ import annotations

import json
from typing import Any

from core_py.bedrock_models import ModelRole, resolve_model_id
from core_py.models import StrategyManifest

_SYSTEM_PROMPT = (
    "You match a free-text software-modernization objective to exactly "
    "one strategy id from a fixed candidate list, or to none if none "
    "genuinely fit. Respond with ONLY a JSON object of the exact shape "
    '{"strategy_id": <id-from-the-list-or-null>, "confidence": <0.0-1.0>} '
    "-- no prose, no markdown fencing. Never return an id that is not in "
    "the candidate list."
)


class NoStrategyMatchError(Exception):
    """Raised when the model returns no id, or an id outside the
    candidate list (treated as no match, never as that match)."""


def _strip_markdown_fence(text: str) -> str:
    """Claude wraps JSON in ```json fences even when told not to
    (confirmed against Haiku 4.5), which would otherwise read as a
    malformed response and be indistinguishable from a real no-match."""

    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    return body.rsplit("```", 1)[0].strip()


def resolve_strategy(
    objetivo: str,
    candidates: list[StrategyManifest],
    *,
    bedrock_client: Any,
    model_id: str | None = None,
) -> tuple[StrategyManifest, float]:
    if not candidates:
        raise NoStrategyMatchError("no strategies are registered")

    resolved_model_id = resolve_model_id(ModelRole.ANALYSIS, override=model_id)
    by_id = {manifest.id: manifest for manifest in candidates}
    catalog = [{"id": manifest.id, "title": manifest.title} for manifest in candidates]

    user_message = json.dumps({"objetivo": objetivo, "candidates": catalog})

    response = bedrock_client.invoke_model(
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

    try:
        parsed = json.loads(_strip_markdown_fence(text))
    except json.JSONDecodeError as exc:
        raise NoStrategyMatchError(f"model response was not valid JSON: {text!r}") from exc

    strategy_id = parsed.get("strategy_id")
    confidence = float(parsed.get("confidence") or 0.0)

    if not strategy_id or strategy_id not in by_id:
        raise NoStrategyMatchError(f"objetivo did not match a registered strategy: {objetivo!r}")

    return by_id[strategy_id], confidence
