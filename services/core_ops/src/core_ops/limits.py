"""Resolves limits through platform ceiling >= strategy max >= request (invariant 5)."""

from __future__ import annotations

from dataclasses import dataclass

from core_py.models import StrategyLimits

LIMIT_FIELDS: tuple[str, ...] = ("max_usd", "max_iterations", "max_minutes")


class LimitsConfigurationError(Exception):
    pass


class LimitsRequestError(Exception):
    pass


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
