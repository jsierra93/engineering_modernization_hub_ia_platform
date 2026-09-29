"""Runs one of the four demo scenarios end to end against the deployed API and prints the outcome.
Creates the run, waits for the plan, approves it, waits for the final state and prints the report summary.
Usage: run_scenario.py exitoso|inviable|inyeccion|prueba_fallida [--no-approve] [--reject] [--max-usd N] [--max-minutes N]
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import boto3

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_DIR = REPO_ROOT / "infrastructure" / "envs"
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-2")
USERNAME = os.environ.get("MODHUB_TEST_USERNAME", "jsierra93@hotmail.com")
OBJETIVO = "Ayudame migrando pydantic v1 a v2 en el proyecto python"

SCENARIOS = {
    "exitoso": ("jsierra93/modhub_sample_success_strategy", "be63acb5636cefa29be393c3a9947e244665e001"),
    "inviable": ("jsierra93/modhub_sample_failed_strategy", "3af994425ce94930e37a721c189e385bc1d1dd13"),
    "inyeccion": ("jsierra93/modhub_sample_prompt_injection", "30434ad7cab4974c593ed5c313f72eaa67fc1558"),
    "prueba_fallida": ("jsierra93/modhub_sample_failed_test", "38dc3118f615b7752381c255a8fa15c2671e99b3"),
}
TERMINAL = {"LISTO_PARA_REVISION", "COMPLETADO_PARCIALMENTE", "BLOQUEADO", "FALLIDO_CONTROLADO", "PRESUPUESTO_AGOTADO", "CANCELADO"}
POLL_SECONDS = 10
PLAN_TIMEOUT_SECONDS = 15 * 60
RUN_TIMEOUT_SECONDS = 30 * 60


def terraform_outputs() -> dict:
    out = subprocess.run(["terraform", "output", "-json"], cwd=ENV_DIR, capture_output=True, text=True, check=True)
    return {name: item["value"] for name, item in json.loads(out.stdout).items()}


def mint_token(outputs: dict) -> str:
    cognito = boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "personal"), region_name=REGION).client("cognito-idp")
    password = os.environ.get("MODHUB_TEST_PASSWORD") or secrets.token_urlsafe(18) + "aA1!"
    pool_id = outputs["cognito_issuer_url"].rsplit("/", 1)[-1]
    cognito.admin_set_user_password(UserPoolId=pool_id, Username=USERNAME, Password=password, Permanent=True)
    auth = cognito.initiate_auth(
        ClientId=outputs["cognito_cli_client_id"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": USERNAME, "PASSWORD": password},
    )
    return auth["AuthenticationResult"]["IdToken"]


def call(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def wait_for(base: str, run_id: str, token: str, stop_states: set[str], timeout: int) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        _, run = call("GET", f"{base}/runs/{run_id}", token)
        status = run.get("status")
        if status != last:
            print(f"  {time.strftime('%H:%M:%S')}  {status}")
            last = status
        if status in stop_states:
            return run
        time.sleep(POLL_SECONDS)
    raise SystemExit(f"timed out waiting for {sorted(stop_states)} (last status: {last})")


def option(name: str, default: float) -> float:
    return float(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in SCENARIOS:
        print(__doc__)
        return 2
    repo, commit = SCENARIOS[sys.argv[1]]
    approve = "--no-approve" not in sys.argv
    decision = "reject" if "--reject" in sys.argv else "approve"
    max_usd, max_minutes = option("--max-usd", 2), option("--max-minutes", 20)

    outputs = terraform_outputs()
    base = outputs["api_endpoint"].rstrip("/") + "/modhub/v1"
    token = mint_token(outputs)

    print(f"==> {sys.argv[1]}: {repo} @ {commit[:12]}")
    status, created = call(
        "POST",
        f"{base}/runs",
        token,
        {"repo": repo, "commit": commit, "objetivo": OBJETIVO, "max_usd": max_usd, "max_iterations": 3, "max_minutes": int(max_minutes), "inputs": {"target_version": "2.11"}},
    )
    if status != 201:
        print(f"create failed: {status} {created}")
        return 1
    run_id = created["run_id"]
    print(f"  run {run_id} strategy {created['resolved_strategy']['id']}")

    run = wait_for(base, run_id, token, TERMINAL | {"AWAITING_APPROVAL"}, PLAN_TIMEOUT_SECONDS)
    if run["status"] == "AWAITING_APPROVAL" and approve:
        print(f"==> {decision} the plan")
        token = mint_token(outputs)
        code, response = call("POST", f"{base}/runs/{run_id}/approval", token, {"decision": decision, "plan_hash": run["plan_hash"]})
        if code != 200:
            print(f"approval failed: {code} {response}")
            return 1
        run = wait_for(base, run_id, token, TERMINAL, RUN_TIMEOUT_SECONDS)

    _, report = call("GET", f"{base}/runs/{run_id}/report", token)
    verdict = report.get("verdict", {})
    print("==> result")
    print(f"  status      {run['status']}  reason_code={run.get('reason_code')}")
    print(f"  spent       ${verdict.get('spent_usd')} of ${verdict.get('max_usd')}  iterations {verdict.get('iterations_used')}/{verdict.get('max_iterations')}")
    print(f"  changed     {run.get('changed_paths')}")
    print(f"  security    {len(report.get('security_events', []))} event(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
