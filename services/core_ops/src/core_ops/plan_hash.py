"""Canonical SHA-256 of a plan, computed by the core and never by the model."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_plan_hash(plan: dict[str, Any]) -> str:
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
