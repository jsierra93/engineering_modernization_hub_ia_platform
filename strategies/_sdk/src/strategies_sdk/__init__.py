"""Strategy contribution SDK.

A strategy module implements `StrategyModule` (a `Protocol`): it exposes a
`manifest()` function returning a `core_py.models.StrategyManifest`.

CLAUDE.md flags this surface as one that "someone can extend without
touching the policy gate" and therefore lacking governance by default --
treat anything a strategy declares as needing review, not as trusted.
This module is that review, made mechanical: `validate_manifest` checks
`inputs` against a JSON-schema-like shape and checks that every declared
`limits.*.max` never exceeds the platform ceiling (CLAUDE.md invariant
#5: platform ceiling >= strategy max >= request -- limits only tighten).
"""

from strategies_sdk.registry import StrategyRegistry
from strategies_sdk.sdk import (
    PLATFORM_CEILING,
    ManifestValidationError,
    PlatformCeiling,
    StrategyModule,
    validate_manifest,
)

__all__ = [
    "PLATFORM_CEILING",
    "ManifestValidationError",
    "PlatformCeiling",
    "StrategyModule",
    "StrategyRegistry",
    "validate_manifest",
]
