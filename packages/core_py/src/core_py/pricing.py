"""Bedrock pricing table -- hand-versioned per CLAUDE.md ("Budget checks
stay local comparisons -- never call a pricing API on the hot path").
Update the rates below when AWS's published Bedrock pricing changes; an
unrecognized model_id fails loudly rather than silently costing $0 and
letting real spend escape the budget ledger unnoticed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenRate:
    input_usd_per_1k: float
    output_usd_per_1k: float


# USD per 1,000 tokens, as of 2026-09-26 (AWS Bedrock on-demand pricing).
# Keyed by the exact model IDs core_py.bedrock_models resolves to -- add a
# row here whenever a new default/override model is qualified.
_RATES_BY_MODEL_ID: dict[str, TokenRate] = {
    "anthropic.claude-haiku-4-5-20251001-v1:0": TokenRate(input_usd_per_1k=0.001, output_usd_per_1k=0.005),
    "anthropic.claude-sonnet-4-5-20250929-v1:0": TokenRate(input_usd_per_1k=0.003, output_usd_per_1k=0.015),
}


class UnknownModelPricingError(Exception):
    """Raised for a model_id with no configured rate."""


_PROFILE_PREFIXES = ("us.", "eu.", "apac.", "global.")


def _bare_model_id(model_id: str) -> str:
    """An inference-profile id ("us.anthropic.claude-...") bills at the
    same rate as the model it routes to, so the prefix is not part of the
    pricing key."""

    for prefix in _PROFILE_PREFIXES:
        if model_id.startswith(prefix):
            return model_id[len(prefix) :]
    return model_id


def estimate_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    rate = _RATES_BY_MODEL_ID.get(_bare_model_id(model_id))
    if rate is None:
        raise UnknownModelPricingError(
            f"no pricing configured for model_id {model_id!r} -- add a rate to "
            f"core_py.pricing before using it in a phase that spends budget."
        )
    return (input_tokens / 1000) * rate.input_usd_per_1k + (output_tokens / 1000) * rate.output_usd_per_1k
