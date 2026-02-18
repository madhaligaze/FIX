from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from policy.unknown_space import apply_unknown_policy
from scanning.next_best_view import generate_scan_plan
from scanning.readiness import compute_readiness
from scaffold.bom import bom_from_elements
from scaffold.solver import generate_scaffold
from scaffold.trace import trace_candidate_grid, trace_solver_start, trace_validator_result
from scaffold.validators import validate_all


router = APIRouter(tags=["planning"])


class ScaffoldRequest(BaseModel):
    session_id: str


@router.post("/planning/request_scaffold")
def request_scaffold(request: Request, payload: ScaffoldRequest):
    state = request.app.state.runtime
    sid = payload.session_id

    world = state.get_world(sid)
    anchors = state.anchors.get(sid, [])

    # STAGE C gate: never generate on BAD tracking
    tq = str(world.metrics.get("tracking_quality", "UNKNOWN"))
    if tq == "BAD":
        scan_plan = generate_scan_plan(world, anchors, state.policy)
        raise HTTPException(
            status_code=409,
            detail={
                "status": "TRACKING_BAD",
                "tracking_reasons": world.metrics.get("tracking_reasons", []),
                "scan_plan": scan_plan,
            },
        )

    ready, score, reasons = compute_readiness(world, anchors, state.policy)
    if not ready:
        scan_plan = generate_scan_plan(world, anchors, state.policy)
        raise HTTPException(
            status_code=409,
            detail={"status": "NOT_READY", "score": score, "reasons": reasons, "scan_plan": scan_plan},
        )

    unknown_report = apply_unknown_policy(world, anchors, state.policy)
    if unknown_report.get("violations"):
        raise HTTPException(status_code=409, detail={"status": "UNKNOWN_VIOLATION", "unknown": unknown_report})

    trace = state.traces.setdefault(sid, [])
    trace_solver_start(trace, {"session_id": sid})

    elements, solver_meta = generate_scaffold(world, anchors, state.policy, trace=trace)
    trace_candidate_grid(trace, solver_meta)

    valid, violations = validate_all(elements, world, state.policy)
    trace_validator_result(trace, valid, violations)
    if not valid:
        raise HTTPException(status_code=409, detail={"status": "VALIDATION_FAILED", "violations": violations})

    bom = bom_from_elements(elements)
    return {"status": "ok", "elements": elements, "bom": bom, "rev_hint": state.last_rev.get(sid)}
