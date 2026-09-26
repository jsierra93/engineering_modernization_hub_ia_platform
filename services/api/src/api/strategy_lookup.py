"""Bootstraps the strategy registry for `create_run`'s objective resolver
(Fase 4, task 4.4). Deliberately duplicated from
services/agent_phase/src/agent_phase/strategy_lookup.py rather than
imported cross-service: api and agent_phase are separately deployable
Lambdas (CLAUDE.md's per-service IAM/packaging philosophy), and each
already copies its own core_py/strategies_sdk sources at build time (see
infrastructure/scripts/build_lambda.sh) -- importing one service's package
from another's handler would blur that boundary for a two-line registry
bootstrap. Growing the catalog means adding one import + one
`.register(...)` call HERE and in agent_phase's copy."""

from __future__ import annotations

from core_py.models import StrategyManifest
from strategies_sdk.registry import StrategyRegistry
from strategies_sdk.sdk import PlatformCeiling

import python_pydantic_v2  # its own __init__.py re-exports manifest() at package level

_PLATFORM_CEILING = PlatformCeiling(max_usd=10, max_iterations=5, max_minutes=60)


def build_registry() -> StrategyRegistry:
    registry = StrategyRegistry(ceiling=_PLATFORM_CEILING)
    registry.register(python_pydantic_v2)
    return registry


def list_strategy_manifests() -> list[StrategyManifest]:
    return build_registry().list()
