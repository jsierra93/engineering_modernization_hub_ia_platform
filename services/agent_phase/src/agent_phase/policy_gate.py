"""The policy gate: Layer 2 of the three-layer defense (see untrusted.py
for Layer 1). CLAUDE.md invariant #3/#4: the agent chooses neither the
command nor its flags, and it writes only inside approved paths. This is
that invariant enforced in code, at the one place Strands calls before any
tool actually executes -- `strands.interventions.InterventionHandler`,
whose own docstring example (a class named `CedarAuth`) is close enough to
this exact use case that it's effectively a confirmation this is the
right mechanism, not a workaround.

Every denial is returned as a `Deny(reason=...)` — Strands turns that into
a tool-result error the model sees, so it can adjust rather than silently
losing a step — and additionally handed to `on_deny` so the caller can
persist a `SecurityBlocked`-shaped event (CLAUDE.md: "Cada denegación
queda en la tabla de eventos"). This module never talks to DynamoDB
itself; logging is the caller's job, this is only the decision.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from core_py.scope import ResolvedScope

from strands.hooks import BeforeToolCallEvent
from strands.interventions import Deny, InterventionHandler, Proceed

# Tools that only ever read (repo content, fetched docs) never need a scope
# check -- the write path is the one that can cause damage. Listing these
# explicitly (rather than "anything not named write_file") means a new
# write-capable tool added later must be deliberately added below, not
# silently allowed by omission.
_UNSCOPED_TOOLS = {"read_file", "list_files", "fetch_doc"}
_SCOPED_WRITE_TOOLS = {"write_file"}


@dataclass
class DenialEvent:
    """What a denial looks like to the caller, for persisting as an event.
    Deliberately plain data -- no dependency on core_py here, so this
    module stays testable without pulling in DynamoDB/moto."""

    tool_name: str
    reason: str
    attempted_path: str | None = None


@dataclass
class WritableScopeGate(InterventionHandler):
    """Denies any write_file call whose path isn't covered by the
    strategy's declared `writable_paths` (glob patterns, e.g.
    `["**/*.py", "pyproject.toml"]` -- see StrategyManifest). Also denies
    any tool call not in the known set at all, so a future tool added to
    `tools.py` without a corresponding gate decision fails closed, not
    open.
    """

    writable_paths: list[str]
    excluded_paths: list[str] = field(default_factory=list)
    on_deny: Callable[[DenialEvent], None] = field(default=lambda _event: None)

    @property
    def name(self) -> str:
        return "writable-scope-gate"

    def _is_writable(self, path: str) -> bool:
        # One implementation of the decision, shared with whatever else
        # checks a path: a second copy is a second place to get `..` wrong.
        return ResolvedScope(
            writable_paths=self.writable_paths,
            excluded_paths=self.excluded_paths,
        ).allows(path)

    def before_tool_call(self, event: BeforeToolCallEvent, **kwargs):
        tool_name = event.tool_use["name"]

        if tool_name in _SCOPED_WRITE_TOOLS:
            path = (event.tool_use.get("input") or {}).get("path")
            if not path or not self._is_writable(path):
                denial = DenialEvent(
                    tool_name=tool_name,
                    reason=f"path {path!r} is not within the run's resolved writable scope",
                    attempted_path=path,
                )
                self.on_deny(denial)
                return Deny(reason=denial.reason)
            return Proceed()

        if tool_name in _UNSCOPED_TOOLS:
            return Proceed()

        # Anything else is a tool this gate has no explicit opinion on --
        # fail closed rather than assume it's safe by default.
        denial = DenialEvent(tool_name=tool_name, reason=f"tool {tool_name!r} is not on the known allowlist")
        self.on_deny(denial)
        return Deny(reason=denial.reason)
