"""Strategy: Pydantic v1 -> v2 migration.

The only real logic here is `manifest()` -- the strategy's contract with
the platform (limits, checks, writable paths, sources). Discovery,
planning, implementation and fix-loop behavior are driven generically by
`agent_phase` (Fase 3 of PLAN.md) reading this manifest; nothing here
executes code inside the sandbox.
"""

from python_pydantic_v2.manifest import manifest

__all__ = ["manifest"]
