"""The strategy contract: what a strategy declares (limits, checks, paths, sources) and nothing about runs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrategyLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: float
    max: float


class StrategyLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_usd: StrategyLimit
    max_iterations: StrategyLimit
    max_minutes: StrategyLimit


class StrategyModelLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_max_tokens: int = 4096
    code_max_tokens: int = 8192


class CheckSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    blocking: bool = True
    baseline: Literal["must_pass", "must_fail", "informational"] | None = None

    @model_validator(mode="after")
    def _default_baseline(self) -> CheckSpec:
        if self.baseline is None:
            self.baseline = "must_pass" if self.blocking else "informational"
        return self


class StrategyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: str
    title: str
    description: str
    ecosystem: str
    sandbox_profile: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    limits: StrategyLimits
    checks: list[CheckSpec]
    writable_paths: list[str]
    excluded_paths: list[str] = Field(default_factory=list)
    sources: list[str]
    model_limits: StrategyModelLimits = Field(default_factory=StrategyModelLimits)
