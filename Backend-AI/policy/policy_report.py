from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def _policy_as_dict(policy: Any) -> dict[str, Any]:
    if is_dataclass(policy):
        return asdict(policy)
    if isinstance(policy, dict):
        return dict(policy)
    return dict(getattr(policy, "__dict__", {}))


def build_policy_report(
    *,
    policy: Any,
    readiness: dict[str, Any] | None = None,
    unknown: dict[str, Any] | None = None,
    validators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    STAGE 8: single compact report object that Android can display.
    """
    policy_dict = _policy_as_dict(policy)
    return {
        "policy": {
            "unknown_mode": str(policy_dict.get("unknown_mode", "forbid")),
            "unknown_buffer_m": float(policy_dict.get("unknown_buffer_m", 0.0)),
            "min_clearance_m": float(policy_dict.get("min_clearance_m", 0.0)),
        },
        "readiness": readiness or {},
        "unknown_space": unknown or {},
        "validators": validators or {},
    }
