"""`plan_hash`: computed here, by the deterministic core, never by the
model. CLAUDE.md's design: the agent proposes a plan; core_ops is what
turns it into the hash the approval endpoint later checks against
(`sub = requested_by`, `plan_hash` match) -- a model asked to compute its
own hash could simply be asked to lie about it, so it never gets the
chance."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_plan_hash(plan: dict[str, Any]) -> str:
    """A canonical (sorted-keys, no extra whitespace) JSON serialization,
    hashed with SHA-256. Canonical form matters: the same plan content
    must always hash the same way regardless of dict insertion order."""

    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
