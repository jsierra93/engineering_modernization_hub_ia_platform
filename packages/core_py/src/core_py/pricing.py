"""Hand-versioned Bedrock price table and local cost estimation.
An unknown model fails loudly instead of costing zero.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenRate:
    input_usd_per_1k: float
    output_usd_per_1k: float


_RATES_BY_MODEL_ID: dict[str, TokenRate] = {
    "anthropic.claude-haiku-4-5-20251001-v1:0": TokenRate(input_usd_per_1k=0.001, output_usd_per_1k=0.005),
    "anthropic.claude-sonnet-4-5-20250929-v1:0": TokenRate(input_usd_per_1k=0.003, output_usd_per_1k=0.015),
}


class UnknownModelPricingError(Exception):
    pass


_PROFILE_PREFIXES = ("us.", "eu.", "apac.", "global.")


def _bare_model_id(model_id: str) -> str:
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
