"""One JSON line per decision, correlated by run_id.

CloudWatch Logs Insights can then reconstruct a whole run across services:

    fields @timestamp, event, phase, status
    | filter run_id = "<id>"
    | sort @timestamp asc
"""

from __future__ import annotations

import json
import sys
from typing import Any


def log_event(event: str, *, run_id: str | None = None, **fields: Any) -> None:
    record: dict[str, Any] = {"event": event}
    if run_id is not None:
        record["run_id"] = str(run_id)
    record.update(fields)
    # print, not logging: Lambda already timestamps stdout, and a bare line
    # stays greppable without a per-service logger config.
    print(json.dumps(record, default=str), file=sys.stdout, flush=True)
