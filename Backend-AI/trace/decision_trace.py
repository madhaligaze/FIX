from __future__ import annotations

import json
import time
import uuid
from typing import Any


def add_trace_event(
    trace: list[dict[str, Any]],
    event: str,
    data: dict[str, Any] | None = None,
    *,
    level: str = "info",
) -> None:
    """
    Stable, machine-readable decision trace events.
    Keep this small; store large payloads as separate artifacts and reference paths.
    """
    if data is None:
        data = {}
    trace.append(
        {
            "id": str(uuid.uuid4()),
            "ts": float(time.time()),
            "event": str(event),
            "level": str(level),
            "data": data,
        }
    )


def add_constraint_eval(
    trace: list[dict[str, Any]],
    *,
    decision_id: str,
    constraint_id: str,
    ok: bool,
    reason: str,
    metrics: dict[str, Any] | None = None,
    element_id: str | None = None,
) -> None:
    add_trace_event(
        trace,
        "constraint_eval",
        {
            "decision_id": str(decision_id),
            "constraint_id": str(constraint_id),
            "ok": bool(ok),
            "reason": str(reason),
            "metrics": metrics or {},
            "element_id": element_id,
        },
    )


def trace_to_ndjson_bytes(trace: list[dict[str, Any]]) -> bytes:
    """
    NDJSON is better for streaming/large traces than a single huge JSON array.
    """
    lines: list[str] = []
    for ev in trace:
        try:
            lines.append(json.dumps(ev, ensure_ascii=False, separators=(",", ":")))
        except Exception:
            # Last-resort fallback to keep trace writable.
            safe = {
                "ts": float(time.time()),
                "event": "trace_serialize_error",
                "data": {"bad_event": str(type(ev))},
            }
            lines.append(json.dumps(safe, ensure_ascii=False, separators=(",", ":")))
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
