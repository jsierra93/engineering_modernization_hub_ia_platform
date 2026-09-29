"""Resolves a logical model role (ANALYSIS, CODE) to a Bedrock model ID.
Order: override argument > environment variable > default. The only place a model ID may be named.
"""

from __future__ import annotations

import os
from enum import Enum


class ModelRole(str, Enum):
    ANALYSIS = "analysis"

    CODE = "code"


_ENV_VAR_BY_ROLE: dict[ModelRole, str] = {
    ModelRole.ANALYSIS: "BEDROCK_MODEL_ANALYSIS",
    ModelRole.CODE: "BEDROCK_MODEL_CODE",
}

_DEFAULT_MODEL_BY_ROLE: dict[ModelRole, str | None] = {
    ModelRole.ANALYSIS: "anthropic.claude-haiku-4-5-20251001-v1:0",
    ModelRole.CODE: "anthropic.claude-haiku-4-5-20251001-v1:0",
}


def resolve_model_id(role: ModelRole, override: str | None = None) -> str:
    if override:
        return override

    env_var = _ENV_VAR_BY_ROLE[role]
    env_value = os.environ.get(env_var)
    if env_value:
        return env_value

    default = _DEFAULT_MODEL_BY_ROLE[role]
    if default is None:
        raise ValueError(
            f"No Bedrock model configured for role {role.value!r}. "
            f"Set the {env_var} environment variable or add a default "
            f"in core_py.bedrock_models."
        )
    return default
