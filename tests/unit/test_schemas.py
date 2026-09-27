"""Structured-output schemas: what the model is allowed to leave out, and
what it can never leave out."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_phase.schemas import DiscoveryPlan, FixAttempt, ImplementationResult


def test_discovery_plan_tolerates_explicit_nulls_for_list_fields():
    """Confirmed against Haiku 4.5 on a real run: the model emitted
    "planned_changes": null rather than omitting the key, and a declared
    default only applies to an absent key."""
    plan = DiscoveryPlan.model_validate(
        {
            "viable": True,
            "viability_reason": "pydantic<2 detected",
            "summary": "Migrate to Pydantic v2",
            "planned_changes": None,
            "sources": None,
            "risks": None,
        }
    )

    assert plan.planned_changes == []
    assert plan.sources == []
    assert plan.risks == []


def test_discovery_plan_still_requires_its_mandatory_fields():
    """Null tolerance must not weaken the fields that carry the decision --
    a plan with no `viable` is a broken response, not an empty one."""
    with pytest.raises(ValidationError):
        DiscoveryPlan.model_validate({"viable": None, "viability_reason": "x", "summary": "y"})


def test_implementation_result_tolerates_nulls():
    result = ImplementationResult.model_validate(
        {"files_changed": None, "tests_added_or_updated": None, "notes": None}
    )

    assert result.files_changed == []
    assert result.tests_added_or_updated == []
    assert result.notes == ""


def test_fix_attempt_tolerates_null_file_list():
    attempt = FixAttempt.model_validate(
        {
            "root_cause": "wrong validator syntax",
            "fix_summary": "updated to field_validator",
            "files_changed": None,
            "confident": True,
        }
    )

    assert attempt.files_changed == []
