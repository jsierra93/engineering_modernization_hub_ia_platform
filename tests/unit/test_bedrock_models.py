"""Bedrock model registry: override > env var > default, and loud
failure when a role has no model configured at all."""

from __future__ import annotations

import pytest

from core_py.bedrock_models import ModelRole, resolve_model_id


def test_analysis_default_is_the_configured_haiku_id():
    assert (
        resolve_model_id(ModelRole.ANALYSIS)
        == "anthropic.claude-haiku-4-5-20251001-v1:0"
    )


def test_env_var_overrides_the_default(monkeypatch):
    monkeypatch.setenv(
        "BEDROCK_MODEL_ANALYSIS", "anthropic.claude-haiku-9000-v1:0"
    )
    assert resolve_model_id(ModelRole.ANALYSIS) == "anthropic.claude-haiku-9000-v1:0"


def test_explicit_override_wins_over_env_var(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ANALYSIS", "anthropic.claude-haiku-9000-v1:0")
    assert (
        resolve_model_id(ModelRole.ANALYSIS, override="anthropic.claude-explicit-v1:0")
        == "anthropic.claude-explicit-v1:0"
    )


def test_code_role_has_no_default_yet_and_fails_loudly():
    with pytest.raises(ValueError, match="No Bedrock model configured"):
        resolve_model_id(ModelRole.CODE)


def test_code_role_works_once_an_env_var_is_set(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_CODE", "anthropic.claude-sonnet-5-v1:0")
    assert resolve_model_id(ModelRole.CODE) == "anthropic.claude-sonnet-5-v1:0"
