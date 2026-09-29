"""Shared models, persistence, scope and pricing for every service.
Re-exports the public surface of core_py.
"""

from core_py.bedrock_models import ModelRole, resolve_model_id
from core_py.observability import log_event
from core_py.pricing import estimate_cost_usd, rate_for
from core_py.scope import ResolvedScope, resolve_scope
from core_py.models import Event, Restricciones, Run, RunStatus
from core_py.strategy_models import StrategyLimit, StrategyLimits, StrategyManifest, StrategyModelLimits

__all__ = [
    "Event",
    "ModelRole",
    "Restricciones",
    "Run",
    "RunStatus",
    "StrategyLimit",
    "StrategyLimits",
    "StrategyManifest",
    "ResolvedScope",
    "StrategyModelLimits",
    "estimate_cost_usd",
    "log_event",
    "rate_for",
    "resolve_model_id",
    "resolve_scope",
]
