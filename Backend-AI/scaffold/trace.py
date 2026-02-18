from __future__ import annotations

from typing import Any

from trace.decision_trace import add_trace_event


def trace_solver_start(trace: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    add_trace_event(trace, "scaffold_solver_start", meta)


def trace_candidate_grid(trace: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    add_trace_event(trace, "scaffold_candidate_grid", meta)


def trace_element_added(trace: list[dict[str, Any]], element: dict[str, Any], reason: str) -> None:
    add_trace_event(trace, "scaffold_element_added", {"element": element, "reason": reason})


def trace_validator_result(trace: list[dict[str, Any]], valid: bool, violations: list[dict[str, Any]]) -> None:
    add_trace_event(trace, "scaffold_validated", {"valid": bool(valid), "violations": violations})
