"""Strands intervention that denies writes outside the resolved scope and any unknown tool.
Denials are reported to the caller; this module never touches DynamoDB.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from core_py.scope import ResolvedScope

from strands.hooks import BeforeToolCallEvent
from strands.interventions import Deny, InterventionHandler, Proceed

_UNSCOPED_TOOLS = {"read_file", "list_files", "fetch_doc"}
_SCOPED_WRITE_TOOLS = {"write_file"}


@dataclass
class DenialEvent:
    tool_name: str
    reason: str
    attempted_path: str | None = None


@dataclass
class WritableScopeGate(InterventionHandler):
    writable_paths: list[str]
    excluded_paths: list[str] = field(default_factory=list)
    on_deny: Callable[[DenialEvent], None] = field(default=lambda _event: None)

    @property
    def name(self) -> str:
        return "writable-scope-gate"

    def _is_writable(self, path: str) -> bool:
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

        # Unknown tools fail closed.
        denial = DenialEvent(tool_name=tool_name, reason=f"tool {tool_name!r} is not on the known allowlist")
        self.on_deny(denial)
        return Deny(reason=denial.reason)
