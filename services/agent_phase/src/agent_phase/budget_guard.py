"""Stops a phase before a model call whose worst case would not fit in what is left of the run's budget (invariant 6).
The worst case is the counted input plus the phase's max_tokens of output. Counting is free and best effort: if it fails the
call proceeds (fail-open) and the ASL's check after the phase still applies.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any

from core_py import estimate_cost_usd, log_event, rate_for
from core_py.pricing import bare_model_id

TOOL_USE_BASE_TOKENS = 600
CHARS_PER_TOKEN = 3

CountTokensFn = Callable[[list[dict[str, Any]], str], int]


def bedrock_count_tokens(model_id: str) -> CountTokensFn:
    import boto3

    client = boto3.client("bedrock-runtime")
    target = bare_model_id(model_id)

    def count(messages: list[dict[str, Any]], system_prompt: str) -> int:
        payload: dict[str, Any] = {"messages": messages}
        if system_prompt:
            payload["system"] = [{"text": system_prompt}]
        return client.count_tokens(modelId=target, input={"converse": payload})["inputTokens"]

    return count


def _tool_overhead_tokens(agent: Any, extra_schema: dict[str, Any] | None) -> int:
    chars = len(json.dumps(agent.tool_registry.get_all_tool_specs(), default=str))
    if extra_schema is not None:
        chars += len(json.dumps(extra_schema, default=str))
    return TOOL_USE_BASE_TOKENS + math.ceil(chars / CHARS_PER_TOKEN)


class BudgetGuard:
    def __init__(
        self,
        *,
        remaining_usd: float | None,
        model_id: str,
        max_output_tokens: int,
        run_id: str = "",
        phase: str = "",
        count_tokens_fn: CountTokensFn | None = None,
    ) -> None:
        self._remaining_usd = remaining_usd
        self._model_id = model_id
        self._max_output_tokens = max_output_tokens
        self._run_id = run_id
        self._phase = phase
        self._count_tokens_fn = count_tokens_fn
        self.stopped = False
        self.reason: str | None = None
        self.skipped_counts = 0

    def _spent_in_phase(self, agent: Any) -> float:
        usage = agent.event_loop_metrics.accumulated_usage
        if usage["inputTokens"] == 0 and usage["outputTokens"] == 0:
            return 0.0
        return estimate_cost_usd(self._model_id, usage["inputTokens"], usage["outputTokens"])

    def _count(self, agent: Any) -> int:
        if self._count_tokens_fn is None:
            self._count_tokens_fn = bedrock_count_tokens(self._model_id)
        system_prompt = agent.system_prompt if isinstance(agent.system_prompt, str) else ""
        messages = [{"role": m["role"], "content": m["content"]} for m in agent.messages]
        return self._count_tokens_fn(messages, system_prompt)

    def check(self, agent: Any, *, extra_schema: dict[str, Any] | None = None) -> bool:
        if self._remaining_usd is None:
            return True
        if self.stopped:
            return False
        try:
            input_tokens = self._count(agent) + _tool_overhead_tokens(agent, extra_schema)
        except Exception as exc:  # noqa: BLE001 - best effort by design
            self.skipped_counts += 1
            log_event("agent_phase.token_precheck_skipped", run_id=self._run_id, phase=self._phase, error=str(exc)[:200])
            return True

        rate = rate_for(self._model_id)
        worst_case = input_tokens * rate.input_usd_per_1k / 1000 + self._max_output_tokens * rate.output_usd_per_1k / 1000
        remaining = self._remaining_usd - self._spent_in_phase(agent)
        if worst_case > remaining:
            self.stopped = True
            self.reason = f"worst case ${worst_case:.4f} exceeds the remaining ${max(remaining, 0.0):.4f}"
            log_event(
                "agent_phase.budget_guard_stopped",
                run_id=self._run_id,
                phase=self._phase,
                input_tokens=input_tokens,
                worst_case_usd=round(worst_case, 6),
                remaining_usd=round(remaining, 6),
            )
            return False
        return True

    def before_model_call(self, event: Any) -> None:
        if not self.check(event.agent):
            event.cancel = f"model call skipped by the budget guard: {self.reason}"
