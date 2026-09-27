"""Bedrock model registry: override > env var > default."""

from __future__ import annotations

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


def test_code_default_is_the_configured_sonnet_id():
    assert (
        resolve_model_id(ModelRole.CODE)
        == "anthropic.claude-sonnet-4-5-20250929-v1:0"
    )


def test_code_role_env_var_overrides_the_default(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_CODE", "anthropic.claude-sonnet-5-v1:0")
    assert resolve_model_id(ModelRole.CODE) == "anthropic.claude-sonnet-5-v1:0"
