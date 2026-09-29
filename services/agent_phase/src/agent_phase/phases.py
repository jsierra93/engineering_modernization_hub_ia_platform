"""One function per phase (discovery_plan, implement, fix) over an already-built agent."""

from __future__ import annotations

from typing import Protocol

from agent_phase.budget_guard import BudgetGuard
from agent_phase.schemas import DiscoveryPlan, FixAttempt, ImplementationResult
from agent_phase.untrusted import wrap_untrusted


class StructuredAgent(Protocol):
    def __call__(self, prompt: str): ...
    def structured_output(self, output_model, prompt=None): ...


def _structured(agent: StructuredAgent, output_model, guard: BudgetGuard | None):
    if guard is not None and (guard.stopped or not guard.check(agent, extra_schema=output_model.model_json_schema())):
        return None
    return agent.structured_output(output_model)


def run_discovery_plan(
    agent: StructuredAgent,
    *,
    objetivo: str,
    strategy_summary: str,
    official_sources: list[str],
    guard: BudgetGuard | None = None,
) -> DiscoveryPlan | None:
    sources = "\n".join(f"- {url}" for url in official_sources)
    prompt = (
        f"Objective (from the developer, free text): {objetivo}\n\n"
        f"Strategy this objective was resolved to: {strategy_summary}\n\n"
        "Explore the repository (list_files, read_file). Before planning, fetch "
        "each official source below with fetch_doc; you may fetch more allowlisted "
        "documentation if the objective needs it. Then produce a complete "
        "DiscoveryPlan. Only cite sources you actually fetched.\n\n"
        f"Official sources for this strategy:\n{sources}"
    )
    agent(prompt)
    return _structured(agent, DiscoveryPlan, guard)


def run_implement(
    agent: StructuredAgent, *, plan: DiscoveryPlan, guard: BudgetGuard | None = None
) -> ImplementationResult | None:
    planned_paths = ", ".join(change.path for change in plan.planned_changes) or "(none listed)"
    prompt = (
        "Implement the following approved plan using write_file. Writes outside "
        "your approved scope will be denied -- if that happens, adjust your "
        "approach rather than retrying the same path.\n\n"
        f"Plan summary: {plan.summary}\n"
        f"Planned files: {planned_paths}\n"
    )
    agent(prompt)
    return _structured(agent, ImplementationResult, guard)


def run_fix(
    agent: StructuredAgent,
    *,
    junit_failure_excerpt: str,
    iteration: int,
    max_iterations: int,
    guard: BudgetGuard | None = None,
) -> FixAttempt | None:
    prompt = (
        f"Verification failed on iteration {iteration} of {max_iterations}. "
        "Analyze the real test output below and apply a fix with write_file, "
        "within your approved scope.\n\n"
        + wrap_untrusted(junit_failure_excerpt, source="junit:verify")
    )
    agent(prompt)
    return _structured(agent, FixAttempt, guard)
