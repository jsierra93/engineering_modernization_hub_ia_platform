"""Registers the strategies this Lambda knows and resolves a manifest by id."""

from __future__ import annotations

from core_py.models import StrategyManifest
from strategies_sdk.registry import StrategyRegistry
from strategies_sdk.sdk import PlatformCeiling

import python_pydantic_v2

_PLATFORM_CEILING = PlatformCeiling(max_usd=10, max_iterations=5, max_minutes=60)


def build_registry() -> StrategyRegistry:
    registry = StrategyRegistry(ceiling=_PLATFORM_CEILING)
    registry.register(python_pydantic_v2)
    return registry


def get_strategy_manifest(strategy_id: str) -> StrategyManifest:
    manifest = build_registry().get(strategy_id)
    if manifest is None:
        raise ValueError(f"no registered strategy with id {strategy_id!r}")
    return manifest
