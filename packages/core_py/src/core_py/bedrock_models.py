"""Bedrock model registry.

Resolves a logical model *role* ("analysis", "code") to a concrete
Bedrock model ID. Existing to satisfy a specific invariant from
CLAUDE.md: "Model choice per phase belongs to the strategy/platform
configuration, never to the agent itself." A phase asks for a role and
gets back whatever is currently configured -- swapping this Haiku for a
newer one, or wiring in Sonnet once it's needed, is a config change,
never a code change, and never a decision the model makes about itself.

Resolution order: explicit override argument > environment variable >
the hardcoded default below. A role with no default (like CODE today)
raises loudly rather than silently falling back to the wrong model.
"""

from __future__ import annotations

import os
from enum import Enum


class ModelRole(str, Enum):
    """A logical role a Bedrock model fills -- not a specific model."""

    ANALYSIS = "analysis"
    """Discovery, impact analysis, plan construction, and the objective
    -> strategy resolver in `services/api` (see CLAUDE.md's "one exception"
    to a fully deterministic core)."""

    CODE = "code"
    """Implementation, test generation, and the fix loop."""


_ENV_VAR_BY_ROLE: dict[ModelRole, str] = {
    ModelRole.ANALYSIS: "BEDROCK_MODEL_ANALYSIS",
    ModelRole.CODE: "BEDROCK_MODEL_CODE",
}

# Defaults as of 2026-09-26. Update here -- or override per-environment
# via the env vars above -- when a new model is qualified. Never
# hardcode a Bedrock model ID anywhere else in the codebase; import
# `resolve_model_id` instead.
#
# Bare IDs work on Floci and in tests; real AWS needs a region-prefixed
# inference-profile ID, which Terraform injects via the env vars above.
_DEFAULT_MODEL_BY_ROLE: dict[ModelRole, str | None] = {
    ModelRole.ANALYSIS: "anthropic.claude-haiku-4-5-20251001-v1:0",
    ModelRole.CODE: "anthropic.claude-sonnet-4-5-20250929-v1:0",
}


def resolve_model_id(role: ModelRole, override: str | None = None) -> str:
    """Resolve the Bedrock model ID to invoke for a given role.

    Raises ValueError if the role has neither an override, an env var,
    nor a default configured -- a misconfiguration should fail loudly,
    not silently invoke a different model than intended.
    """
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
