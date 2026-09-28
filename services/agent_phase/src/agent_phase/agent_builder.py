"""Assembles a real Strands Agent for one phase invocation.

Every choice here is one CLAUDE.md already made, not a free decision this
module gets to revisit:
  - temperature=0 (invariant: reproducibility during the live defense)
  - max_tokens comes from the strategy's StrategyModelLimits, never chosen
    by the agent itself
  - the model ID comes from core_py.bedrock_models.resolve_model_id, never
    hardcoded here
  - the policy gate (WritableScopeGate) is always attached; there is no
    code path that constructs an Agent without one
  - the system prompt always includes the untrusted-content clause

The Bedrock Guardrail is deliberately NOT a constructor kwarg on
`BedrockModel`: see `guardrail.py` for why screening the whole turn
blocks the platform's own instructions. It is handed to `build_tools`
instead, which applies it to repo and document content only.
"""

from __future__ import annotations

from collections.abc import Callable

from core_py import ModelRole, resolve_model_id
from strands import Agent
from strands.models import BedrockModel

from agent_phase.guardrail import Guardrail
from agent_phase.policy_gate import DenialEvent, WritableScopeGate
from agent_phase.tools import FetchDocFn, OnBlockFn, build_tools
from agent_phase.untrusted import UNTRUSTED_CONTENT_SYSTEM_PROMPT_CLAUSE
from agent_phase.workspace import Workspace

SYSTEM_PROMPT = f"""You are the proposing side of a modernization pipeline whose \
core principle is "el LLM propone, el núcleo dispone" -- you analyze, plan, and \
write code, but you never decide whether a run succeeds. A separate, \
Bedrock-free component computes the final verdict from the real test suite, \
not from anything you say.

You can only write files within the paths your policy gate allows -- a write \
outside that scope is denied before it happens, and denials are logged as \
security events, not silently ignored.

{UNTRUSTED_CONTENT_SYSTEM_PROMPT_CLAUSE}

Always cite the actual sources you consulted via fetch_doc. Never claim a plan \
step you didn't perform, and never assert that tests pass -- you don't run \
them; the sandbox does, independently."""


def build_agent(
    *,
    role: ModelRole,
    max_tokens: int,
    workspace: Workspace,
    fetch_doc_fn: FetchDocFn,
    writable_paths: list[str],
    excluded_paths: list[str] | None = None,
    on_deny: Callable[[DenialEvent], None] | None = None,
    guardrail: Guardrail | None = None,
    on_block: OnBlockFn | None = None,
    region_name: str | None = None,
    include_write_tool: bool = True,
) -> Agent:
    bedrock_kwargs: dict = {
        "model_id": resolve_model_id(role),
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    model = BedrockModel(region_name=region_name, **bedrock_kwargs)
    gate = WritableScopeGate(
        writable_paths=writable_paths,
        excluded_paths=excluded_paths or [],
        on_deny=on_deny or (lambda _e: None),
    )
    tools = build_tools(
        workspace,
        fetch_doc_fn,
        include_write=include_write_tool,
        guardrail=guardrail,
        on_block=on_block,
    )

    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        interventions=[gate],
    )
