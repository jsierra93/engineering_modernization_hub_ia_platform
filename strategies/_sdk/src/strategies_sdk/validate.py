"""Pre-registration check for every discovered strategy: manifest rules, unique ids, and that its
sandbox profile exists and offers every check the strategy declares. Run it with scripts/validate-strategies.sh.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from core_py.limits import platform_ceiling

from strategies_sdk.discovery import discover_strategy_modules
from strategies_sdk.sdk import ManifestValidationError, validate_manifest


def _profile_checks(repo_root: Path, profile: str) -> set[str] | None:
    path = repo_root / "sandbox" / "profiles" / f"{profile}.json"
    if not path.is_file():
        return None
    return set(json.loads(path.read_text(encoding="utf-8"))["checks"])


def validate_all(repo_root: Path) -> list[str]:
    errors: list[str] = []
    modules = discover_strategy_modules()
    if not modules:
        errors.append("no strategy found: a strategy package must ship a strategy.marker file")
    seen: dict[str, str] = {}
    for module in modules:
        try:
            manifest = module.manifest()
            validate_manifest(manifest, platform_ceiling())
        except ManifestValidationError as exc:
            errors.append(f"{module.__name__}: {exc}")
            continue
        if manifest.id in seen:
            errors.append(f"{module.__name__}: id {manifest.id!r} already used by {seen[manifest.id]}")
        seen[manifest.id] = module.__name__

        available = _profile_checks(repo_root, manifest.sandbox_profile)
        if available is None:
            errors.append(f"{module.__name__}: sandbox profile {manifest.sandbox_profile!r} has no sandbox/profiles file")
            continue
        for check in manifest.checks:
            if check.name not in available:
                errors.append(f"{module.__name__}: profile {manifest.sandbox_profile!r} cannot run check {check.name!r}")

        checks = ", ".join(f"{c.name}{'' if c.blocking else '*'}" for c in manifest.checks)
        print(f"ok  {manifest.id:<28} {manifest.ecosystem:<8} sandbox: {manifest.sandbox_profile:<8} checks: {checks}  ({module.__name__})")
    return errors


def main() -> int:
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    errors = validate_all(repo_root)
    for error in errors:
        print(f"FAIL {error}")
    if not errors:
        print("(* = non-blocking)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
