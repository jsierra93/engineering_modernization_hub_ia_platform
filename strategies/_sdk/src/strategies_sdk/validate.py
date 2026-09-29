"""Pre-registration check for every discovered strategy: manifest rules, unique ids, and that
each declared check is one the sandbox can actually run. Run it with scripts/validate-strategies.sh.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from core_py.constants import CHECK_VOCABULARY
from core_py.limits import platform_ceiling

from strategies_sdk.discovery import discover_strategy_modules
from strategies_sdk.sdk import ManifestValidationError, validate_manifest


def _sandbox_checks(repo_root: Path) -> set[str]:
    tree = ast.parse((repo_root / "sandbox" / "entrypoint.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "KNOWN_CHECKS" for t in node.targets):
            return set(ast.literal_eval(node.value))
    raise RuntimeError("sandbox/entrypoint.py does not define KNOWN_CHECKS")


def validate_all(repo_root: Path) -> list[str]:
    errors: list[str] = []
    sandbox = _sandbox_checks(repo_root)
    for name in CHECK_VOCABULARY:
        if name not in sandbox:
            errors.append(f"platform vocabulary lists {name!r} but the sandbox cannot run it")

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
        checks = ", ".join(f"{c.name}{'' if c.blocking else '*'}" for c in manifest.checks)
        print(f"ok  {manifest.id:<28} {manifest.ecosystem:<8} checks: {checks}  ({module.__name__})")
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
