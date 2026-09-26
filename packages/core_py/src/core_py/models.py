"""Pydantic v2 models shared across services.

These mirror the schemas in packages/contracts/openapi.yaml (`Run`,
`Event`, `StrategyManifest`, ...). The OpenAPI spec is the source of truth
for the wire shape; these models must round-trip against it (see
tests/unit/test_models_openapi_roundtrip.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(str, Enum):
    """The run lifecycle.

    PENDING, AWAITING_APPROVAL and RUNNING are in-flight. CANCELADO is a
    human decision, not a modernization outcome. The remaining five are
    the final states core_ops evaluates in this strict order (first match
    wins), per CLAUDE.md:

        PRESUPUESTO_AGOTADO > BLOQUEADO > FALLIDO_CONTROLADO >
        COMPLETADO_PARCIALMENTE > LISTO_PARA_REVISION
    """

    PENDING = "PENDING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    RUNNING = "RUNNING"
    CANCELADO = "CANCELADO"
    PRESUPUESTO_AGOTADO = "PRESUPUESTO_AGOTADO"
    BLOQUEADO = "BLOQUEADO"
    FALLIDO_CONTROLADO = "FALLIDO_CONTROLADO"
    COMPLETADO_PARCIALMENTE = "COMPLETADO_PARCIALMENTE"
    LISTO_PARA_REVISION = "LISTO_PARA_REVISION"


# The ordered tuple of final states core_ops must evaluate, first match
# wins. Exposed as a module-level constant (an Enum cannot cleanly hold an
# aggregate member of its own type).
FINAL_STATES_ORDER: tuple[RunStatus, ...] = (
    RunStatus.PRESUPUESTO_AGOTADO,
    RunStatus.BLOQUEADO,
    RunStatus.FALLIDO_CONTROLADO,
    RunStatus.COMPLETADO_PARCIALMENTE,
    RunStatus.LISTO_PARA_REVISION,
)


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class Restricciones(BaseModel):
    model_config = ConfigDict(extra="forbid")

    excluded_paths: list[str] = Field(default_factory=list)


class Run(BaseModel):
    """Mirrors `#/components/schemas/Run` in packages/contracts/openapi.yaml."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    run_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    status: RunStatus = RunStatus.PENDING
    repo: str
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
    iterations_used: int = 0
    plan_hash: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def model_dump_json_shape(self) -> dict[str, Any]:
        """`model_dump(mode="json")` with run_id/commit as plain strings,
        matching the OpenAPI `Run` schema exactly."""
        return self.model_dump(mode="json")


class Event(BaseModel):
    """Mirrors `#/components/schemas/Event`."""

    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    seq: int = Field(ge=0)
    type: str
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


class StrategyLimit(BaseModel):
    """A single tunable limit: the strategy's own default, and the max a
    request may raise it to (never above the platform ceiling)."""

    model_config = ConfigDict(extra="forbid")

    default: float
    max: float


class StrategyLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_usd: StrategyLimit
    max_iterations: StrategyLimit
    max_minutes: StrategyLimit


class StrategyManifest(BaseModel):
    """Mirrors `#/components/schemas/StrategyManifest`.

    `inputs` is a JSON-schema-like dict describing the strategy's own
    request inputs (validated by strategies/_sdk, not by this model).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    version: str
    title: str
    applies_to: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    limits: StrategyLimits
    checks: list[str]
    writable_paths: list[str]
    sources: list[str]
