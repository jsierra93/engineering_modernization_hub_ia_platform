"""Bedrock Guardrails applied to untrusted content only (CLAUDE.md
invariant #9, Layer 2).

Attaching the guardrail to the model invocation itself -- the obvious
wiring, and what this module replaces -- screens the *whole* turn. A
PROMPT_ATTACK filter at HIGH strength reads the platform's own imperative
instructions to the agent ("implement this plan", "writes outside your
scope will be denied") as an attempted prompt attack and blocks the call:
the phase then returns zero tokens and an empty result. That is a false
positive on trusted input, and it silently costs the run its entire
implement phase.

The filter's actual job is to screen what comes from the repository or a
fetched document. Calling ApplyGuardrail on exactly that content, and
nothing else, is both the correct scope and the one the design document
describes.
"""

from __future__ import annotations

import os
from typing import Any

GUARDRAIL_ID_ENV = "MODHUB_BEDROCK_GUARDRAIL_ID"
GUARDRAIL_VERSION_ENV = "MODHUB_BEDROCK_GUARDRAIL_VERSION"


class UntrustedContentBlocked(Exception):
    def __init__(self, source: str, assessment: Any = None) -> None:
        super().__init__(f"guardrail blocked untrusted content from {source}")
        self.source = source
        self.assessment = assessment


class Guardrail:
    def __init__(self, guardrail_id: str, version: str, *, client: Any = None, region_name: str | None = None):
        self._id = guardrail_id
        self._version = version
        self._client = client
        self._region = region_name

    @classmethod
    def from_env(cls, *, client: Any = None, region_name: str | None = None) -> Guardrail | None:
        guardrail_id = os.environ.get(GUARDRAIL_ID_ENV)
        if not guardrail_id:
            return None
        version = os.environ.get(GUARDRAIL_VERSION_ENV) or "DRAFT"
        return cls(guardrail_id, version, client=client, region_name=region_name)

    def _bedrock(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=self._region)
        return self._client

    def screen(self, content: str, *, source: str) -> None:
        """Raise UntrustedContentBlocked if the guardrail rejects `content`."""

        response = self._bedrock().apply_guardrail(
            guardrailIdentifier=self._id,
            guardrailVersion=self._version,
            source="INPUT",
            content=[{"text": {"text": content}}],
        )
        if response.get("action") == "GUARDRAIL_INTERVENED":
            raise UntrustedContentBlocked(source, response.get("assessments"))
