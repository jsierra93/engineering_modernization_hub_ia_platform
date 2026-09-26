"""Structured-output schemas for each agent_phase phase.

Forcing the model's response into one of these schemas (via Strands'
`structured_output_model`) is the "Plan-and-Solve" pattern named in the
design artifact's Uso de IA section: the model commits to a complete,
parseable plan before a single change is made, rather than deciding
step-by-step as it goes. It also closes a real failure mode named in the
artifact's retrospective -- free-text output that breaks `plan_hash`
computation -- by construction: a `DiscoveryPlan` either validates against
this schema or the call fails loudly, there is no malformed-but-plausible
middle ground.

None of these schemas grant the model any authority. `core_ops` (a
different, Bedrock-free component) is what turns a `DiscoveryPlan` into a
`plan_hash` and what turns a `FixAttempt`'s test run into a verdict --
these are just structured requests, never decisions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlannedFileChange(BaseModel):
    """One file the plan proposes to touch. `path` is checked against the
    strategy's `writable_paths` by the policy gate at write time -- listing
    a path here does not grant permission to write it."""

    path: str
    reason: str = Field(description="Why this file needs to change, in one sentence.")


class DiscoveryPlan(BaseModel):
    """Output of the DiscoveryPlan phase: what the repo needs, whether it's
    viable, and what's proposed -- before any write happens."""

    viable: bool = Field(description="Whether this modernization can be completed within the given constraints.")
    viability_reason: str = Field(description="Why viable, or why not -- cites sources where relevant.")
    summary: str = Field(description="One-paragraph summary of what will change and why.")
    planned_changes: list[PlannedFileChange] = Field(default_factory=list)
    sources: list[str] = Field(
        default_factory=list,
        description="URLs actually consulted via the fetch_doc tool -- not invented citations.",
    )
    risks: list[str] = Field(default_factory=list, description="Known risks or edge cases this plan doesn't cover.")


class FileEdit(BaseModel):
    """One file actually written during Implement or a fix iteration."""

    path: str
    summary: str = Field(description="One-sentence description of what changed in this file.")


class ImplementationResult(BaseModel):
    """Output of the Implement phase: what was actually written, matched
    against what the plan proposed. The policy gate is what actually
    enforces `writable_paths` at write time -- this schema records the
    agent's own account of what it did, for the report."""

    files_changed: list[FileEdit] = Field(default_factory=list)
    tests_added_or_updated: list[str] = Field(
        default_factory=list, description="Test file paths added or updated -- never a claim that they pass."
    )
    notes: str = Field(default="", description="Anything the report should mention about the implementation.")


class FixAttempt(BaseModel):
    """Output of a fix iteration: analysis of a real JUnit failure and a
    proposed (then applied, through the same write_file tool and gate)
    correction. `test_failure_excerpt` is untrusted-adjacent (it can
    contain assertion messages derived from repo content) but is treated
    as data throughout -- the model analyzes it, it never becomes an
    instruction."""

    root_cause: str = Field(description="What in the failing test output indicates the actual bug.")
    fix_summary: str = Field(description="What was changed to address it, in one paragraph.")
    files_changed: list[FileEdit] = Field(default_factory=list)
    confident: bool = Field(description="Whether the model believes this fix addresses the root cause.")
