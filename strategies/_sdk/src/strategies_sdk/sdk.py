"""Strategy Protocol and manifest validation against the platform ceiling (invariant 5)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core_py.limits import LIMIT_FIELDS, PlatformCeiling, platform_ceiling
from core_py.models import StrategyManifest

PLATFORM_CEILING = platform_ceiling()


class ManifestValidationError(ValueError):
    pass


@runtime_checkable
class StrategyModule(Protocol):
    def manifest(self) -> StrategyManifest: ...


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

    ceiling_values = ceiling.as_dict()
    for field in LIMIT_FIELDS:
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
