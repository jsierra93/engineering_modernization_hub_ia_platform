"""Builds the Strands agent for one phase: temperature 0, strategy max_tokens, policy gate always attached.
The guardrail is applied to untrusted content in the tools, not to the whole turn.
"""

from __future__ import annotations

from collections.abc import Callable

from core_py import ModelRole, resolve_model_id
from strands import Agent
from strands.hooks import BeforeModelCallEvent
from strands.models import BedrockModel

from agent_phase.budget_guard import BudgetGuard
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
    budget_guard: BudgetGuard | None = None,
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

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        interventions=[gate],
    )
    if budget_guard is not None:
        agent.hooks.add_callback(BeforeModelCallEvent, budget_guard.before_model_call)
    return agent
