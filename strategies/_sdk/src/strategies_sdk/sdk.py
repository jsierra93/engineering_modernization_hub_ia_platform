"""Strategy Protocol and manifest validation against the platform ceiling (invariant 5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from core_py.models import StrategyManifest


@dataclass(frozen=True)
class PlatformCeiling:
    max_usd: float
    max_iterations: int
    max_minutes: int


PLATFORM_CEILING = PlatformCeiling(max_usd=10.0, max_iterations=5, max_minutes=60)


class ManifestValidationError(ValueError):
    pass


@runtime_checkable
class StrategyModule(Protocol):
    def manifest(self) -> StrategyManifest: ...


_LIMIT_FIELDS = ("max_usd", "max_iterations", "max_minutes")


def _validate_inputs_schema(inputs: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(inputs, dict):
        return ["inputs must be an object"]

    for name, spec in inputs.items():
        if not isinstance(spec, dict):
            errors.append(f"inputs.{name} must be an object describing the field")
            continue
        if "type" not in spec:
            errors.append(f"inputs.{name} is missing 'type'")
        if spec.get("required") and "enum" in spec and not spec["enum"]:
            errors.append(f"inputs.{name} declares an empty enum")

    return errors


def validate_manifest(
    manifest: StrategyManifest,
    ceiling: PlatformCeiling = PLATFORM_CEILING,
) -> None:
    errors: list[str] = []

    errors.extend(_validate_inputs_schema(manifest.inputs))

    ceiling_values = {
        "max_usd": ceiling.max_usd,
        "max_iterations": ceiling.max_iterations,
        "max_minutes": ceiling.max_minutes,
    }
    for field in _LIMIT_FIELDS:
        limit = getattr(manifest.limits, field)
        ceiling_value = ceiling_values[field]
        if limit.max > ceiling_value:
            errors.append(
                f"limits.{field}.max ({limit.max}) exceeds the platform ceiling "
                f"({ceiling_value})"
            )
        if limit.default > limit.max:
            errors.append(
                f"limits.{field}.default ({limit.default}) exceeds limits.{field}.max "
                f"({limit.max})"
            )

    if not manifest.checks:
        errors.append("checks must declare at least one named check")
    if not manifest.writable_paths:
        errors.append("writable_paths must declare at least one path")
    if not manifest.sources:
        errors.append("sources must cite at least one official source")

    if errors:
        raise ManifestValidationError("; ".join(errors))
