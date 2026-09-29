"""Scores one or more Bedrock models on the objective-to-strategy resolver with the real prompt and fixed cases.
Run it before changing resolver_model_id; the catalog and cases live in scripts/resolver_cases.json.
Usage: eval_resolver.py MODEL_ID [MODEL_ID ...] [--rate MODEL=IN,OUT ...] [--min-accuracy 0.9]
A rate is USD per million tokens. The exit code is 1 when the first model scores below --min-accuracy.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import boto3

from api.resolver import NoStrategyMatchError, ResolverUnavailableError, resolve_strategy
from python_pydantic_v2.manifest import manifest

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-2")
CASES_FILE = Path(__file__).with_name("resolver_cases.json")


class CountingClient:
    def __init__(self, client):
        self._client = client
        self.input_tokens = 0
        self.output_tokens = 0

    def converse(self, **kwargs):
        response = self._client.converse(**kwargs)
        usage = response.get("usage", {})
        self.input_tokens += usage.get("inputTokens", 0)
        self.output_tokens += usage.get("outputTokens", 0)
        return response


def load_catalog(entries):
    base = manifest()
    return [base.model_copy(update=entry) for entry in entries]


def evaluate(model_id: str, catalog, cases):
    client = CountingClient(boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "personal"), region_name=REGION).client("bedrock-runtime"))
    right, misses, errors, latencies = 0, [], 0, []
    for case in cases:
        started = time.time()
        try:
            chosen, _ = resolve_strategy(case["objetivo"], catalog, bedrock_client=client, model_id=model_id)
            got = chosen.id
        except NoStrategyMatchError:
            got = None
        except ResolverUnavailableError as exc:
            errors += 1
            got = f"ERROR {str(exc)[:70]}"
        latencies.append(time.time() - started)
        if got == case["expected"]:
            right += 1
        else:
            misses.append((case["objetivo"][:52], case["expected"], got))
    calls = len(cases)
    return {
        "right": right,
        "calls": calls,
        "errors": errors,
        "misses": misses,
        "latency": sum(latencies) / calls,
        "input_tokens": client.input_tokens / calls,
        "output_tokens": client.output_tokens / calls,
    }


def parse_args(argv):
    models, rates, min_accuracy = [], {}, 0.9
    i = 0
    while i < len(argv):
        if argv[i] == "--rate":
            model, pair = argv[i + 1].split("=", 1)
            rates[model] = tuple(float(x) for x in pair.split(","))
            i += 2
        elif argv[i] == "--min-accuracy":
            min_accuracy = float(argv[i + 1])
            i += 2
        else:
            models.append(argv[i])
            i += 1
    return models, rates, min_accuracy


def main() -> int:
    models, rates, min_accuracy = parse_args(sys.argv[1:])
    if not models:
        print(__doc__)
        return 2
    spec = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    catalog = load_catalog(spec["catalog"])

    first_accuracy = None
    for model_id in models:
        result = evaluate(model_id, catalog, spec["cases"])
        accuracy = result["right"] / result["calls"]
        first_accuracy = accuracy if first_accuracy is None else first_accuracy
        cost = ""
        if model_id in rates:
            rate_in, rate_out = rates[model_id]
            per_call = result["input_tokens"] * rate_in / 1e6 + result["output_tokens"] * rate_out / 1e6
            cost = f"  costo/llamada ${per_call:.6f}"
        print(
            f"\n{model_id}\n  aciertos {result['right']}/{result['calls']}  errores {result['errors']}  "
            f"latencia {result['latency']:.2f}s  tokens in={result['input_tokens']:.0f} out={result['output_tokens']:.0f}{cost}"
        )
        for objetivo, expected, got in result["misses"]:
            print(f"   x {objetivo!r}: esperaba {expected}, obtuvo {got}")
    return 0 if first_accuracy >= min_accuracy else 1


if __name__ == "__main__":
    raise SystemExit(main())
