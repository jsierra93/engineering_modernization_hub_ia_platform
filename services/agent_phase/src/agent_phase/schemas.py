"""Structured outputs the agent must return for each phase."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class _NullTolerant(BaseModel):
    """Models routinely emit `"field": null` for "nothing here" instead of
    omitting the key, and a declared default only applies to an absent key.
    Dropping nulls lets the defaults below do their job, while a genuinely
    required field with no default still fails loudly."""

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if value is not None}
        return data


class PlannedFileChange(BaseModel):
    """One file the plan proposes to touch. `path` is checked against the
    strategy's `writable_paths` by the policy gate at write time -- listing
    a path here does not grant permission to write it."""

    path: str
    reason: str = Field(description="Why this file needs to change, in one sentence.")


class DiscoveryPlan(_NullTolerant):
    """Output of the DiscoveryPlan phase: what the repo needs, whether it's
    viable, and what's proposed -- before any write happens."""

    viable: bool = Field(description="Whether this modernization can be completed within the given constraints.")
    viability_reason: str = Field(description="Why viable, or why not -- cites sources where relevant.")
    summary: str = Field(
        default="",
        description="One-paragraph summary of what will change and why. Required when viable.",
    )
    planned_changes: list[PlannedFileChange] = Field(default_factory=list)
    sources: list[str] = Field(
        default_factory=list,
        description="URLs actually consulted via the fetch_doc tool -- not invented citations.",
    )
    risks: list[str] = Field(default_factory=list, description="Known risks or edge cases this plan doesn't cover.")

    @model_validator(mode="after")
    def _summary_required_when_viable(self) -> DiscoveryPlan:
        """A plain required `summary` turned a correct conclusion into a
        platform error: asked to summarise "what will change" on a repo it
        had just ruled out, the model omitted the field, validation failed,
        and a reasoned infeasibility surfaced as FALLIDO_CONTROLADO instead
        of BLOQUEADO -- the exact confusion invariant #11 exists to prevent.
        The guarantee is kept where it means something: a viable plan still
        has to say what it will do."""

        if self.viable and not self.summary.strip():
            raise ValueError("summary is required when viable is true")
        return self


class FileEdit(BaseModel):
    """One file actually written during Implement or a fix iteration."""

    path: str
    summary: str = Field(description="One-sentence description of what changed in this file.")


class ImplementationResult(_NullTolerant):
    """Output of the Implement phase: what was actually written, matched
    against what the plan proposed. The policy gate is what actually
    enforces `writable_paths` at write time -- this schema records the
    agent's own account of what it did, for the report."""

    files_changed: list[FileEdit] = Field(default_factory=list)
    tests_added_or_updated: list[str] = Field(
        default_factory=list, description="Test file paths added or updated -- never a claim that they pass."
    )
    notes: str = Field(default="", description="Anything the report should mention about the implementation.")


class FixAttempt(_NullTolerant):
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
