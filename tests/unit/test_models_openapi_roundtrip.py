"""Task 1.3: Run/Event/StrategyManifest must round-trip against the
OpenAPI schema in packages/contracts/openapi.yaml -- models are derived
from the contract, not the other way around.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from core_py.models import Event, Restricciones, Run, RunStatus, StrategyLimit, StrategyLimits, StrategyManifest

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "packages" / "contracts" / "openapi.yaml"
)


def _load_contract() -> dict:
    with CONTRACT_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _run_schema_properties() -> dict:
    contract = _load_contract()
    return contract["components"]["schemas"]["Run"]["properties"]


def test_run_round_trip_matches_openapi_run_schema():
    run = Run(
        repo="https://github.com/example/demo",
        commit="a" * 40,
        objetivo="Migrate to Pydantic v2",
        requested_by="user-123",
        strategy_id="python-pydantic-v2",
        strategy_version="1.0.0",
        max_usd=5.0,
        max_iterations=3,
        max_minutes=20,
        restricciones=Restricciones(excluded_paths=["**/ci/**"]),
    )

    dumped = run.model_dump(mode="json")
    schema_properties = _run_schema_properties()

    # Every field the OpenAPI Run schema requires must be present.
    required = _load_contract()["components"]["schemas"]["Run"]["required"]
    for field in required:
        assert field in dumped, f"Run.model_dump is missing required field {field!r}"

    # Every field the model emits must be a field the schema knows about.
    for field in dumped:
        assert field in schema_properties, f"Run emits undeclared field {field!r}"

    assert dumped["status"] == RunStatus.PENDING.value
    assert isinstance(dumped["run_id"], str)
    assert isinstance(dumped["commit"], str)


def test_run_status_enum_matches_openapi_enum():
    contract = _load_contract()
    openapi_values = set(contract["components"]["schemas"]["RunStatus"]["enum"])
    model_values = {member.value for member in RunStatus}
    assert model_values == openapi_values


def test_event_round_trip_matches_openapi_event_schema():
    import uuid

    event = Event(run_id=uuid.uuid4(), seq=0, type="RunCreated", message="created")
    dumped = event.model_dump(mode="json")

    contract = _load_contract()
    schema = contract["components"]["schemas"]["Event"]
    for field in schema["required"]:
        assert field in dumped
    for field in dumped:
        assert field in schema["properties"]


def test_strategy_manifest_round_trip_matches_openapi_schema():
    manifest = StrategyManifest(
        id="dummy",
        version="1.0.0",
        title="Dummy",
        inputs={"target_version": {"type": "string", "required": True}},
        limits=StrategyLimits(
            max_usd=StrategyLimit(default=1.0, max=2.0),
            max_iterations=StrategyLimit(default=1, max=2),
            max_minutes=StrategyLimit(default=10, max=20),
        ),
        checks=["install"],
        writable_paths=["**/*.py"],
        sources=["https://example.com"],
    )
    dumped = manifest.model_dump(mode="json")

    contract = _load_contract()
    schema = contract["components"]["schemas"]["StrategyManifest"]
    for field in schema["required"]:
        assert field in dumped
    for field in dumped:
        assert field in schema["properties"]
