"""Registers the strategies this Lambda knows and lists their manifests."""

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


def list_strategy_manifests() -> list[StrategyManifest]:
    return build_registry().list()
