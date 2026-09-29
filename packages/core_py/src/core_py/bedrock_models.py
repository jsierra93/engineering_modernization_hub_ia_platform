"""Resolves a logical model role (ANALYSIS, CODE) to a Bedrock model ID.
Order: override argument > environment variable. No model is named in code; Terraform owns the choice.
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


def resolve_model_id(role: ModelRole, override: str | None = None) -> str:
    if override:
        return override

    env_var = _ENV_VAR_BY_ROLE[role]
    env_value = os.environ.get(env_var)
    if not env_value:
        raise ValueError(f"No Bedrock model configured for role {role.value!r}: set {env_var}.")
    return env_value
