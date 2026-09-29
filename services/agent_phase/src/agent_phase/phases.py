"""One function per phase (discovery_plan, implement, fix) over an already-built agent."""

from __future__ import annotations

from typing import Protocol

from agent_phase.schemas import DiscoveryPlan, FixAttempt, ImplementationResult
from agent_phase.untrusted import wrap_untrusted


class StructuredAgent(Protocol):
    def __call__(self, prompt: str): ...
    def structured_output(self, output_model, prompt=None): ...


def run_discovery_plan(agent: StructuredAgent, *, objetivo: str, strategy_summary: str) -> DiscoveryPlan:
    prompt = (
        f"Objective (from the developer, free text): {objetivo}\n\n"
        f"Strategy this objective was resolved to: {strategy_summary}\n\n"
        "Explore the repository (list_files, read_file), consult official "
        "documentation as needed (fetch_doc), and produce a complete "
        "DiscoveryPlan. Only cite sources you actually fetched."
    )
    agent(prompt)
    return agent.structured_output(DiscoveryPlan)


def run_implement(agent: StructuredAgent, *, plan: DiscoveryPlan) -> ImplementationResult:
    planned_paths = ", ".join(change.path for change in plan.planned_changes) or "(none listed)"
    prompt = (
        "Implement the following approved plan using write_file. Writes outside "
        "your approved scope will be denied -- if that happens, adjust your "
        "approach rather than retrying the same path.\n\n"
        f"Plan summary: {plan.summary}\n"
        f"Planned files: {planned_paths}\n"
    )
    agent(prompt)
    return agent.structured_output(ImplementationResult)


def run_fix(
    agent: StructuredAgent,
    *,
    junit_failure_excerpt: str,
    iteration: int,
    max_iterations: int,
) -> FixAttempt:
    prompt = (
        f"Verification failed on iteration {iteration} of {max_iterations}. "
        "Analyze the real test output below and apply a fix with write_file, "
        "within your approved scope.\n\n"
        + wrap_untrusted(junit_failure_excerpt, source="junit:verify")
    )
    agent(prompt)
    return agent.structured_output(FixAttempt)
