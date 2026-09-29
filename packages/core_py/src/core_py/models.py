"""Pydantic models mirroring packages/contracts/openapi.yaml (Run, Event, StrategyManifest).
The OpenAPI spec is the source of truth for the wire shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(str, Enum):
    PENDING = "PENDING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    RUNNING = "RUNNING"
    CANCELADO = "CANCELADO"
    PRESUPUESTO_AGOTADO = "PRESUPUESTO_AGOTADO"
    BLOQUEADO = "BLOQUEADO"
    FALLIDO_CONTROLADO = "FALLIDO_CONTROLADO"
    COMPLETADO_PARCIALMENTE = "COMPLETADO_PARCIALMENTE"
    LISTO_PARA_REVISION = "LISTO_PARA_REVISION"


class Restricciones(BaseModel):
    model_config = ConfigDict(extra="forbid")

    excluded_paths: list[str] = Field(default_factory=list)


class Run(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    run_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    status: RunStatus = RunStatus.PENDING
    repo: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
    commit: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    objetivo: str = Field(min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    restricciones: Restricciones = Field(default_factory=Restricciones)
    requested_by: str
    strategy_id: str
    strategy_version: str
    max_usd: float = Field(gt=0)
    max_iterations: int = Field(ge=1)
    max_minutes: int = Field(ge=1)
    spent_usd: float = 0.0
    models_used: dict[str, str] = Field(default_factory=dict)
    iterations_used: int = 0
    plan_hash: str | None = None
    awaiting_approval_since: datetime | None = None
    approval_wait_seconds: float = 0.0
    reason_code: str | None = None
    diff_key: str | None = None
    changed_paths: list[str] = Field(default_factory=list)
    pull_request_url: str | None = None
    pull_request_branch: str | None = None
    plan: dict[str, Any] | None = None
    task_token: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    seq: int = Field(ge=0)
    type: str
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


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
    inputs: dict[str, Any] = Field(default_factory=dict)
    limits: StrategyLimits
    checks: list[CheckSpec]
    writable_paths: list[str]
    excluded_paths: list[str] = Field(default_factory=list)
    sources: list[str]
    model_limits: StrategyModelLimits = Field(default_factory=StrategyModelLimits)
