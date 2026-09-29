"""The one place the strategy catalog is assembled; every service reads it from here.
Strategies are discovered by their strategy.marker file, so adding one needs no edit here.
"""

from __future__ import annotations

from core_py.limits import platform_ceiling
from core_py.strategy_models import StrategyManifest


def build_registry():
    from strategies_sdk.discovery import discover_strategy_modules
    from strategies_sdk.registry import StrategyRegistry

    registry = StrategyRegistry(ceiling=platform_ceiling())
    for module in discover_strategy_modules():
        registry.register(module)
    return registry


def list_strategy_manifests() -> list[StrategyManifest]:
    return build_registry().list()


def get_strategy_manifest(strategy_id: str) -> StrategyManifest:
    manifest = build_registry().get(strategy_id)
    if manifest is None:
        raise ValueError(f"no registered strategy with id {strategy_id!r}")
    return manifest
