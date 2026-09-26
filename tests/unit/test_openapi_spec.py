"""Task 1.2: the OpenAPI spec must validate cleanly."""

from __future__ import annotations

from pathlib import Path

from openapi_spec_validator import validate

import yaml

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "packages" / "contracts" / "openapi.yaml"
)

EXPECTED_ROUTES = {
    "/me",
    "/strategies",
    "/runs",
    "/runs/{run_id}",
    "/runs/{run_id}/events",
    "/runs/{run_id}/plan",
    "/runs/{run_id}/approval",
    "/runs/{run_id}/cancellation",
    "/runs/{run_id}/diff",
    "/runs/{run_id}/report",
}


def _load_contract() -> dict:
    with CONTRACT_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_openapi_spec_is_valid():
    spec = _load_contract()
    validate(spec)


def test_openapi_spec_covers_all_eleven_routes():
    spec = _load_contract()
    paths = spec["paths"]
    assert EXPECTED_ROUTES <= set(paths.keys())

    # /runs has both POST and GET -> that's the 11th route.
    http_methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    operation_count = sum(
        len(http_methods & ops.keys()) for ops in paths.values()
    )
    assert operation_count == 11


def test_error_schema_matches_code_message_run_id():
    spec = _load_contract()
    error_schema = spec["components"]["schemas"]["Error"]
    assert set(error_schema["required"]) == {"code", "message", "run_id"}


def test_create_run_returns_201_and_422_no_strategy_match():
    spec = _load_contract()
    post_runs = spec["paths"]["/runs"]["post"]
    responses = post_runs["responses"]
    assert "201" in responses
    assert "422" in responses
