"""Bedrock Guardrails applied only to untrusted content (invariant 9).
A missing configuration fails the phase unless explicitly opted out.
"""

from __future__ import annotations

import os
from typing import Any

GUARDRAIL_ID_ENV = "MODHUB_BEDROCK_GUARDRAIL_ID"
GUARDRAIL_VERSION_ENV = "MODHUB_BEDROCK_GUARDRAIL_VERSION"
GUARDRAIL_OPTIONAL_ENV = "MODHUB_GUARDRAIL_OPTIONAL"


class GuardrailNotConfiguredError(Exception):
    pass


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
        if os.environ.get(GUARDRAIL_OPTIONAL_ENV, "").lower() in ("1", "true", "yes"):
            return None

        guardrail_id = os.environ.get(GUARDRAIL_ID_ENV)
        if not guardrail_id:
            raise GuardrailNotConfiguredError(
                f"{GUARDRAIL_ID_ENV} is not set. Set it, or set "
                f"{GUARDRAIL_OPTIONAL_ENV}=true to run without the prompt-attack filter."
            )
        version = os.environ.get(GUARDRAIL_VERSION_ENV) or "DRAFT"
        return cls(guardrail_id, version, client=client, region_name=region_name)

    def _bedrock(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=self._region)
        return self._client

    def screen(self, content: str, *, source: str) -> None:
        response = self._bedrock().apply_guardrail(
            guardrailIdentifier=self._id,
            guardrailVersion=self._version,
            source="INPUT",
            content=[{"text": {"text": content}}],
        )
        if response.get("action") == "GUARDRAIL_INTERVENED":
            raise UntrustedContentBlocked(source, response.get("assessments"))
