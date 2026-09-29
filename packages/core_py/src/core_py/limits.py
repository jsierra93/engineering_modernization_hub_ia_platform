"""Platform ceiling and limit resolution: ceiling >= strategy max >= request (invariant 5).
The ceiling is read from MODHUB_CEILING_* (set by Terraform); the defaults below apply when unset.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from core_py.models import StrategyLimits

LIMIT_FIELDS: tuple[str, ...] = ("max_usd", "max_iterations", "max_minutes")

DEFAULT_CEILING_MAX_USD = 10.0
DEFAULT_CEILING_MAX_ITERATIONS = 5
DEFAULT_CEILING_MAX_MINUTES = 60


@dataclass(frozen=True)
class PlatformCeiling:
    max_usd: float
    max_iterations: int
    max_minutes: int

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def platform_ceiling() -> PlatformCeiling:
    return PlatformCeiling(
        max_usd=float(os.environ.get("MODHUB_CEILING_MAX_USD", DEFAULT_CEILING_MAX_USD)),
        max_iterations=int(os.environ.get("MODHUB_CEILING_MAX_ITERATIONS", DEFAULT_CEILING_MAX_ITERATIONS)),
        max_minutes=int(os.environ.get("MODHUB_CEILING_MAX_MINUTES", DEFAULT_CEILING_MAX_MINUTES)),
    )


class LimitsConfigurationError(Exception):
    pass


class LimitsRequestError(Exception):
    def __init__(self, message: str, *, field: str, requested: float, maximum: float) -> None:
        super().__init__(message)
        self.field = field
        self.requested = requested
        self.maximum = maximum


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
                    f"strategy's max of {strategy_limit.max}",
                    field=field_name,
                    requested=requested_value,
                    maximum=strategy_limit.max,
                )
            resolved[field_name] = requested_value
        else:
            resolved[field_name] = strategy_limit.default

    return ResolvedLimits(
        max_usd=resolved["max_usd"],
        max_iterations=int(resolved["max_iterations"]),
        max_minutes=int(resolved["max_minutes"]),
    )
