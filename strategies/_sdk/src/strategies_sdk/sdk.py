"""Strategy Protocol and manifest validation against the platform ceiling (invariant 5)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core_py.constants import CHECK_VOCABULARY
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


def _validate_checks(manifest: StrategyManifest) -> list[str]:
    names = [check.name for check in manifest.checks]
    errors = [
        f"checks.{name} is not in the platform vocabulary {list(CHECK_VOCABULARY)}"
        for name in names
        if name not in CHECK_VOCABULARY
    ]
    if len(set(names)) != len(names):
        errors.append("checks must not repeat a name")
    if not any(check.blocking for check in manifest.checks):
        errors.append("checks must declare at least one blocking check")
    for check in manifest.checks:
        if check.blocking and check.baseline == "informational":
            errors.append(f"checks.{check.name} is blocking, so its baseline must be must_pass or must_fail")
        if not check.blocking and check.baseline != "informational":
            errors.append(f"checks.{check.name} is non-blocking, so its baseline must be informational")
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

    errors.extend(_validate_checks(manifest))
    if not manifest.description.strip():
        errors.append("description must say what the strategy does, in one sentence")
    if not manifest.ecosystem.strip() or manifest.ecosystem != manifest.ecosystem.lower():
        errors.append("ecosystem must be a non-empty lowercase name such as \"python\"")
    if not manifest.writable_paths:
        errors.append("writable_paths must declare at least one path")
    if not manifest.sources:
        errors.append("sources must cite at least one official source")

    if errors:
        raise ManifestValidationError("; ".join(errors))
