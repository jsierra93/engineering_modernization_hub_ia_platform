"""Structured JSON logging: one line per decision, correlated by run_id and trace_id."""

from __future__ import annotations

import json
import sys
from typing import Any


def log_event(
    event: str,
    *,
    run_id: str | None = None,
    trace_id: str | None = None,
    **fields: Any
) -> None:
    record: dict[str, Any] = {"event": event}
    if run_id is not None:
        record["run_id"] = str(run_id)
    if trace_id is not None:
        record["trace_id"] = str(trace_id)
    record.update(fields)
    print(json.dumps(record, default=str), file=sys.stdout, flush=True)
