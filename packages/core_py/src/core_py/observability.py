"""One JSON line per decision, correlated by run_id and trace_id.

CloudWatch Logs Insights can then reconstruct a whole run across services:

    fields @timestamp, event, phase, status, trace_id
    | filter run_id = "<id>"
    | sort @timestamp asc

Or by trace_id for entire request flow:

    fields @timestamp, event, service, status, trace_id
    | filter trace_id = "<id>"
    | sort @timestamp asc
"""

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
    """Log a structured event with run_id and trace_id for tracing.
    
    Args:
        event: Event name (e.g., "strategy_resolved", "approval_approved")
        run_id: Run identifier for correlation
        trace_id: Trace identifier for distributed tracing (W3C format)
        **fields: Additional fields to include in the log record
    """
    record: dict[str, Any] = {"event": event}
    if run_id is not None:
        record["run_id"] = str(run_id)
    if trace_id is not None:
        record["trace_id"] = str(trace_id)
    record.update(fields)
    # print, not logging: Lambda already timestamps stdout, and a bare line
    # stays greppable without a per-service logger config.
    print(json.dumps(record, default=str), file=sys.stdout, flush=True)
