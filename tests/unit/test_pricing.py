from __future__ import annotations

import pytest

from core_py.pricing import UnknownModelPricingError, estimate_cost_usd


def test_estimate_cost_usd_for_configured_model():
    cost = estimate_cost_usd("anthropic.claude-haiku-4-5-20251001-v1:0", input_tokens=1000, output_tokens=200)
    assert cost == pytest.approx(0.001 + 0.001)


def test_estimate_cost_usd_raises_for_unknown_model():
    with pytest.raises(UnknownModelPricingError):
        estimate_cost_usd("anthropic.claude-does-not-exist", input_tokens=1, output_tokens=1)
