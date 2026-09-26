"""Task 3.5: the policy gate is the concrete enforcement of CLAUDE.md
invariants #3/#4 -- these tests are the ones that actually matter for the
whole "el LLM propone, el núcleo dispone" thesis, since this is the one
place a model's tool call gets a real allow/deny decision."""

from __future__ import annotations

from strands.hooks.events import BeforeToolCallEvent
from strands.interventions import Deny, Proceed

from agent_phase.policy_gate import DenialEvent, WritableScopeGate


def _event(tool_name: str, tool_input: dict | None = None) -> BeforeToolCallEvent:
    return BeforeToolCallEvent(
        agent=None,  # gate never touches .agent
        selected_tool=None,
        tool_use={"name": tool_name, "input": tool_input or {}, "toolUseId": "t1"},
        invocation_state={},
    )


def test_write_within_writable_paths_proceeds():
    gate = WritableScopeGate(writable_paths=["**/*.py", "pyproject.toml"])
    result = gate.before_tool_call(_event("write_file", {"path": "src/models.py", "content": "x"}))
    assert isinstance(result, Proceed)


def test_write_outside_writable_paths_is_denied():
    denials: list[DenialEvent] = []
    gate = WritableScopeGate(writable_paths=["**/*.py"], on_deny=denials.append)

    result = gate.before_tool_call(_event("write_file", {"path": "infrastructure/main.tf", "content": "x"}))

    assert isinstance(result, Deny)
    assert len(denials) == 1
    assert denials[0].attempted_path == "infrastructure/main.tf"


def test_write_to_excluded_ci_path_is_denied_even_if_pattern_looks_close():
    """Mirrors the design's own excluded_paths example (**/ci/** stays
    off-limits even for a Python-file-shaped strategy)."""
    gate = WritableScopeGate(writable_paths=["**/*.py"])  # ci workflow files aren't *.py at all
    result = gate.before_tool_call(_event("write_file", {"path": ".github/workflows/ci.yml", "content": "x"}))
    assert isinstance(result, Deny)


def test_write_with_missing_path_is_denied_not_crashed():
    gate = WritableScopeGate(writable_paths=["**/*.py"])
    result = gate.before_tool_call(_event("write_file", {}))
    assert isinstance(result, Deny)


def test_read_only_tools_always_proceed():
    gate = WritableScopeGate(writable_paths=[])  # even with nothing writable
    for tool_name in ("read_file", "list_files", "fetch_doc"):
        result = gate.before_tool_call(_event(tool_name, {"path": "anything"}))
        assert isinstance(result, Proceed), tool_name


def test_unknown_tool_fails_closed():
    """A tool this gate has no opinion on must be denied, not silently
    allowed -- CLAUDE.md's 'no free shell' invariant extended to any tool
    nobody explicitly reviewed."""
    denials: list[DenialEvent] = []
    gate = WritableScopeGate(writable_paths=["**/*"], on_deny=denials.append)

    result = gate.before_tool_call(_event("run_shell_command", {"cmd": "rm -rf /"}))

    assert isinstance(result, Deny)
    assert denials[0].tool_name == "run_shell_command"


def test_on_deny_callback_is_optional():
    """Default no-op on_deny must not raise -- a caller that doesn't care
    about event logging (e.g. a quick script) shouldn't be forced to
    supply one."""
    gate = WritableScopeGate(writable_paths=[])
    result = gate.before_tool_call(_event("write_file", {"path": "x.py"}))
    assert isinstance(result, Deny)
