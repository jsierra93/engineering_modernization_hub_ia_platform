"""Per-model token pricing read from configuration, and local cost estimation.
Terraform owns the table (MODHUB_MODEL_PRICING); a model without a rate fails loudly instead of costing zero.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

MODEL_PRICING_ENV = "MODHUB_MODEL_PRICING"
_PROFILE_PREFIXES = ("us.", "eu.", "apac.", "global.")


@dataclass(frozen=True)
class TokenRate:
    input_usd_per_1k: float
    output_usd_per_1k: float


class UnknownModelPricingError(Exception):
    pass


def bare_model_id(model_id: str) -> str:
    for prefix in _PROFILE_PREFIXES:
        if model_id.startswith(prefix):
            return model_id[len(prefix) :]
    return model_id


def _load_rates() -> dict[str, TokenRate]:
    raw = os.environ.get(MODEL_PRICING_ENV)
    if not raw:
        raise UnknownModelPricingError(f"{MODEL_PRICING_ENV} is not set -- no model has a configured price")
    try:
        return {model: TokenRate(**rate) for model, rate in json.loads(raw).items()}
    except (ValueError, TypeError, AttributeError) as exc:
        raise UnknownModelPricingError(f"{MODEL_PRICING_ENV} is malformed: {exc}") from exc


def rate_for(model_id: str) -> TokenRate:
    rates = _load_rates()
    rate = rates.get(model_id) or rates.get(bare_model_id(model_id))
    if rate is None:
        raise UnknownModelPricingError(f"no pricing configured for model_id {model_id!r} in {MODEL_PRICING_ENV}")
    return rate


def estimate_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    rate = rate_for(model_id)
    return (input_tokens / 1000) * rate.input_usd_per_1k + (output_tokens / 1000) * rate.output_usd_per_1k
