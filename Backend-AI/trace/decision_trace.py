from __future__ import annotations

import time
from typing import Any


def add_trace_event(trace: list[dict[str, Any]], event_type: str, details: dict[str, Any]) -> None:
    trace.append({"timestamp": time.time(), "type": event_type, "details": details})
