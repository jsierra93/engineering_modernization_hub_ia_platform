"""Task 2.6: resolve_limits' three-level hierarchy -- platform ceiling >=
strategy max >= request, each level can only tighten."""

from __future__ import annotations

import pytest

from core_ops.limits import (
    LimitsConfigurationError,
    LimitsRequestError,
    resolve_limits,
)
from core_py.models import StrategyLimit, StrategyLimits

PLATFORM_CEILING = {"max_usd": 10.0, "max_iterations": 5, "max_minutes": 60}

STRATEGY_LIMITS = StrategyLimits(
    max_usd=StrategyLimit(default=2.0, max=5.0),
    max_iterations=StrategyLimit(default=3, max=5),
    max_minutes=StrategyLimit(default=20, max=45),
)


def test_no_request_inherits_strategy_defaults():
    resolved = resolve_limits(None, STRATEGY_LIMITS, PLATFORM_CEILING)

    assert resolved.max_usd == 2.0
    assert resolved.max_iterations == 3
    assert resolved.max_minutes == 20


def test_request_within_strategy_max_is_honored():
    resolved = resolve_limits(
        {"max_usd": 4.0, "max_iterations": 5, "max_minutes": 30},
        STRATEGY_LIMITS,
        PLATFORM_CEILING,
    )

    assert resolved.max_usd == 4.0
    assert resolved.max_iterations == 5
    assert resolved.max_minutes == 30


def test_request_above_strategy_max_is_rejected():
    with pytest.raises(LimitsRequestError):
        resolve_limits({"max_usd": 9.0}, STRATEGY_LIMITS, PLATFORM_CEILING)


def test_request_above_strategy_max_iterations_is_rejected():
    with pytest.raises(LimitsRequestError):
        resolve_limits({"max_iterations": 100}, STRATEGY_LIMITS, PLATFORM_CEILING)


def test_strategy_max_above_platform_ceiling_is_a_configuration_error():
    broken_strategy = StrategyLimits(
        max_usd=StrategyLimit(default=2.0, max=50.0),  # exceeds ceiling of 10
        max_iterations=StrategyLimit(default=3, max=5),
        max_minutes=StrategyLimit(default=20, max=45),
    )

    with pytest.raises(LimitsConfigurationError):
        resolve_limits(None, broken_strategy, PLATFORM_CEILING)


def test_partial_request_fills_remaining_fields_from_strategy_default():
    resolved = resolve_limits({"max_usd": 3.0}, STRATEGY_LIMITS, PLATFORM_CEILING)

    assert resolved.max_usd == 3.0
    assert resolved.max_iterations == 3  # strategy default
    assert resolved.max_minutes == 20  # strategy default
