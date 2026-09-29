"""Finds strategy packages by a marker file, so registering a strategy never means editing a list.
A strategy is any top-level package that ships a `strategy.marker` file and exposes manifest().
"""

from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache
from pathlib import Path
from types import ModuleType

MARKER_FILE = "strategy.marker"


@lru_cache(maxsize=1)
def discover_strategy_modules() -> tuple[ModuleType, ...]:
    modules = []
    for info in pkgutil.iter_modules():
        finder_path = getattr(info.module_finder, "path", None)
        if not info.ispkg or finder_path is None:
            continue
        if (Path(finder_path) / info.name / MARKER_FILE).is_file():
            modules.append(importlib.import_module(info.name))
    return tuple(sorted(modules, key=lambda module: module.__name__))
