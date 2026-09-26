"""One function per ASL phase, each taking an already-built agent.

Task 3.3's own scope is proving this wiring works without Bedrock: every
function here takes a `StructuredAgent` (a Protocol satisfied by both the
real `strands.Agent` and a trivial test double), so the phase-dispatch
logic, prompt construction, and untrusted-content handling are all
testable without ever calling `agent_builder.build_agent`. Task 3.4 is
`agent_builder.build_agent` actually being used to produce the real agent
these functions receive in production (see `handler.py`).
"""

from __future__ import annotations

from typing import Protocol

from agent_phase.schemas import DiscoveryPlan, FixAttempt, ImplementationResult
from agent_phase.untrusted import wrap_untrusted


class StructuredAgent(Protocol):
    def structured_output(self, output_model, prompt=None): ...


def run_discovery_plan(agent: StructuredAgent, *, objetivo: str, strategy_summary: str) -> DiscoveryPlan:
    """Phase: DiscoveryPlan. Explores the repo, consults docs, commits to
    a complete plan before anything is written (Plan-and-Solve, per the
    design artifact's Uso de IA section)."""

    prompt = (
        f"Objective (from the developer, free text): {objetivo}\n\n"
        f"Strategy this objective was resolved to: {strategy_summary}\n\n"
        "Explore the repository (list_files, read_file), consult official "
        "documentation as needed (fetch_doc), and produce a complete "
        "DiscoveryPlan. Only cite sources you actually fetched."
    )
    return agent.structured_output(DiscoveryPlan, prompt)


def run_implement(agent: StructuredAgent, *, plan: DiscoveryPlan) -> ImplementationResult:
    """Phase: Implement. Writes code within the approved plan's scope --
    the policy gate, not this function, is what actually stops a write
    outside writable_paths."""

    planned_paths = ", ".join(change.path for change in plan.planned_changes) or "(none listed)"
    prompt = (
        "Implement the following approved plan using write_file. Writes outside "
        "your approved scope will be denied -- if that happens, adjust your "
        "approach rather than retrying the same path.\n\n"
        f"Plan summary: {plan.summary}\n"
        f"Planned files: {planned_paths}\n"
    )
    return agent.structured_output(ImplementationResult, prompt)


def run_fix(
    agent: StructuredAgent,
    *,
    junit_failure_excerpt: str,
    iteration: int,
    max_iterations: int,
) -> FixAttempt:
    """Phase: a single fix iteration (task 3.8's fix loop). The JUnit
    excerpt is real pytest output from the sandbox -- CLAUDE.md invariant
    #2's "Critic-Revise" pattern, where the critic is the real test run,
    not the model evaluating itself. Wrapped as untrusted content: it can
    contain arbitrary text from assertion messages or captured stdout that
    originated in the repository being modernized."""

    prompt = (
        f"Verification failed on iteration {iteration} of {max_iterations}. "
        "Analyze the real test output below and apply a fix with write_file, "
        "within your approved scope.\n\n"
        + wrap_untrusted(junit_failure_excerpt, source="junit:verify")
    )
    return agent.structured_output(FixAttempt, prompt)
