"""In-process strategy registry; validates each manifest on registration."""

from __future__ import annotations

from core_py.strategy_models import StrategyManifest

from strategies_sdk.sdk import PlatformCeiling, StrategyModule, validate_manifest


class StrategyRegistry:
    def __init__(self, ceiling: PlatformCeiling | None = None) -> None:
        self._ceiling = ceiling
        self._manifests: dict[str, StrategyManifest] = {}

    def register(self, module: StrategyModule) -> StrategyManifest:
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
