"""Task 3.4: proves the real Bedrock wiring is assembled correctly --
model ID from the registry (never hardcoded), temperature 0 (CLAUDE.md:
reproducibility during the live defense), max_tokens from the strategy,
guardrail wired in when configured. Does NOT invoke Bedrock (no real AWS
credentials in this environment) -- constructing BedrockModel/Agent makes
no network call, so this is real object-construction verification, not a
mock standing in for the whole thing."""

from __future__ import annotations

from strands.interventions import Deny, Proceed

from agent_phase.agent_builder import build_agent
from agent_phase.policy_gate import DenialEvent


class _DictWorkspace:
    def __init__(self):
        self.files: dict[str, str] = {}

    def read(self, path):
        return self.files[path]

    def write(self, path, content):
        self.files[path] = content

    def list(self, prefix=""):
        return [p for p in self.files if p.startswith(prefix)]


def test_build_agent_uses_the_resolved_model_id_and_temperature_zero():
    agent = build_agent(
        role=__import__("core_py").ModelRole.ANALYSIS,
        max_tokens=4096,
        workspace=_DictWorkspace(),
        fetch_doc_fn=lambda url: "x",
        writable_paths=["**/*.py"],
    )

    config = agent.model.get_config()
    assert config["model_id"] == "anthropic.claude-haiku-4-5-20251001-v1:0"
    assert config["temperature"] == 0
    assert config["max_tokens"] == 4096


def test_build_agent_uses_the_configured_sonnet_id_for_code_role(monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_CODE", raising=False)
    from core_py import ModelRole

    agent = build_agent(
        role=ModelRole.CODE,
        max_tokens=8192,
        workspace=_DictWorkspace(),
        fetch_doc_fn=lambda url: "x",
        writable_paths=["**/*.py"],
    )
    assert agent.model.get_config()["model_id"] == "anthropic.claude-sonnet-4-5-20250929-v1:0"


def test_build_agent_wires_the_policy_gate_as_the_only_intervention():
    agent = build_agent(
        role=__import__("core_py").ModelRole.ANALYSIS,
        max_tokens=1024,
        workspace=_DictWorkspace(),
        fetch_doc_fn=lambda url: "x",
        writable_paths=["**/*.py"],
    )

    # Agent has no public accessor for its registered interventions as of
    # strands-agents 1.57.1 -- `.handlers` on the (underscore-prefixed)
    # registry is the least-private way to inspect what got wired in.
    handlers = agent._intervention_registry.handlers
    assert len(handlers) == 1
    gate = handlers[0]
    assert gate.name == "writable-scope-gate"
    assert gate.writable_paths == ["**/*.py"]


def test_build_agent_omits_guardrail_config_when_not_provided():
    agent = build_agent(
        role=__import__("core_py").ModelRole.ANALYSIS,
        max_tokens=1024,
        workspace=_DictWorkspace(),
        fetch_doc_fn=lambda url: "x",
        writable_paths=["**/*.py"],
    )
    config = agent.model.get_config()
    assert "guardrail_id" not in config or config.get("guardrail_id") is None


def test_build_agent_wires_guardrail_when_provided():
    agent = build_agent(
        role=__import__("core_py").ModelRole.ANALYSIS,
        max_tokens=1024,
        workspace=_DictWorkspace(),
        fetch_doc_fn=lambda url: "x",
        writable_paths=["**/*.py"],
        guardrail_id="gr-abc123",
        guardrail_version="1",
    )
    config = agent.model.get_config()
    assert config["guardrail_id"] == "gr-abc123"
    assert config["guardrail_version"] == "1"


def test_build_agent_exposes_the_four_tools():
    agent = build_agent(
        role=__import__("core_py").ModelRole.ANALYSIS,
        max_tokens=1024,
        workspace=_DictWorkspace(),
        fetch_doc_fn=lambda url: "x",
        writable_paths=["**/*.py"],
    )
    tool_names = set(agent.tool_registry.registry.keys())
    assert tool_names == {"read_file", "list_files", "write_file", "fetch_doc"}


def test_on_deny_callback_reaches_the_caller_through_the_wired_gate():
    denials: list[DenialEvent] = []
    agent = build_agent(
        role=__import__("core_py").ModelRole.ANALYSIS,
        max_tokens=1024,
        workspace=_DictWorkspace(),
        fetch_doc_fn=lambda url: "x",
        writable_paths=["**/*.py"],
        on_deny=denials.append,
    )
    gate = agent._intervention_registry.handlers[0]
    from strands.hooks.events import BeforeToolCallEvent

    result = gate.before_tool_call(
        BeforeToolCallEvent(
            agent=None,
            selected_tool=None,
            tool_use={"name": "write_file", "input": {"path": "secret.env"}, "toolUseId": "t1"},
            invocation_state={},
        )
    )
    assert isinstance(result, Deny)
    assert len(denials) == 1
    assert denials[0].attempted_path == "secret.env"
