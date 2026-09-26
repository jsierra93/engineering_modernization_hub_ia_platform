"""PLAN.md task 2.6 -- `resolve_limits`: the three-level limit hierarchy
from CLAUDE.md invariant #5: "platform ceiling (Terraform) >= strategy max
(`manifest().limits`) >= request. Never let a request raise a ceiling."

Each level can only tighten, never loosen. Both failure modes raise
loudly rather than silently clamping, matching the pattern already
established in `core_py.bedrock_models.resolve_model_id` (a
misconfiguration should fail loudly, not silently do something else):

- a request asking for more than the strategy's own max -> `LimitsRequestError`
- a strategy whose own max exceeds the platform ceiling -> `LimitsConfigurationError`
  (this is a factory/authoring bug -- it should never happen, but a
  strategy is untrusted contribution surface per CLAUDE.md's repository
  layout notes, so it is checked anyway, every time).
"""

from __future__ import annotations

from dataclasses import dataclass

from core_py.models import StrategyLimits

LIMIT_FIELDS: tuple[str, ...] = ("max_usd", "max_iterations", "max_minutes")


class LimitsConfigurationError(Exception):
    """The strategy's own max exceeds the platform ceiling. A factory
    invariant violation -- never a request's fault."""


class LimitsRequestError(Exception):
    """The caller requested a limit above what the strategy allows."""


@dataclass(frozen=True)
class ResolvedLimits:
    max_usd: float
    max_iterations: int
    max_minutes: int


def resolve_limits(
    requested: dict[str, float] | None,
    strategy: StrategyLimits,
    platform_ceiling: dict[str, float],
) -> ResolvedLimits:
    """Resolve the three-level limit hierarchy for one field at a time.

    `requested` may omit any field (or be `None` entirely) to inherit the
    strategy's own default for that field.
    """

    requested = requested or {}
    resolved: dict[str, float] = {}

    for field_name in LIMIT_FIELDS:
        strategy_limit = getattr(strategy, field_name)
        ceiling_value = platform_ceiling[field_name]

        if strategy_limit.max > ceiling_value:
            raise LimitsConfigurationError(
                f"strategy limit {field_name}.max={strategy_limit.max} exceeds "
                f"the platform ceiling {ceiling_value} -- this must never happen "
                f"and indicates a broken strategy manifest, not a bad request."
            )

        if field_name in requested:
            requested_value = requested[field_name]
            if requested_value > strategy_limit.max:
                raise LimitsRequestError(
                    f"requested {field_name}={requested_value} exceeds the "
                    f"strategy's max of {strategy_limit.max}"
                )
            resolved[field_name] = requested_value
        else:
            resolved[field_name] = strategy_limit.default

    return ResolvedLimits(
        max_usd=resolved["max_usd"],
        max_iterations=int(resolved["max_iterations"]),
        max_minutes=int(resolved["max_minutes"]),
    )
