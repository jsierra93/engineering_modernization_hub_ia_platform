"""The one place the strategy catalog is assembled; every service reads it from here.
Adding a strategy means registering it in build_registry and nowhere else.
"""

from __future__ import annotations

from core_py.limits import platform_ceiling
from core_py.models import StrategyManifest


def build_registry():
    import python_pydantic_v2
    from strategies_sdk.registry import StrategyRegistry

    registry = StrategyRegistry(ceiling=platform_ceiling())
    registry.register(python_pydantic_v2)
    return registry


def list_strategy_manifests() -> list[StrategyManifest]:
    return build_registry().list()


def get_strategy_manifest(strategy_id: str) -> StrategyManifest:
    manifest = build_registry().get(strategy_id)
    if manifest is None:
        raise ValueError(f"no registered strategy with id {strategy_id!r}")
    return manifest
