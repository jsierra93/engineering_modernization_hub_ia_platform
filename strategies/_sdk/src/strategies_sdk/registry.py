"""A tiny in-process strategy registry.

CLAUDE.md: "the strategy registry drives GET /modhub/v1/strategies, the
Scaffolder form and local CLI validation. Never hardcode a strategy list
anywhere else." This is that registry's minimal, dependency-free form for
the prototype: strategies register their `manifest()` callable and the
registry validates it on load.
"""

from __future__ import annotations

from core_py.models import StrategyManifest

from strategies_sdk.sdk import PlatformCeiling, StrategyModule, validate_manifest


class StrategyRegistry:
    def __init__(self, ceiling: PlatformCeiling | None = None) -> None:
        self._ceiling = ceiling
        self._manifests: dict[str, StrategyManifest] = {}

    def register(self, module: StrategyModule) -> StrategyManifest:
        """Load, validate and register a strategy module's manifest.

        Raises `strategies_sdk.ManifestValidationError` if the manifest
        fails validation -- an invalid strategy never enters the catalog.
        """

        manifest = module.manifest()
        if self._ceiling is not None:
            validate_manifest(manifest, self._ceiling)
        else:
            validate_manifest(manifest)
        self._manifests[manifest.id] = manifest
        return manifest

    def get(self, strategy_id: str) -> StrategyManifest | None:
        return self._manifests.get(strategy_id)

    def list(self) -> list[StrategyManifest]:
        return list(self._manifests.values())
