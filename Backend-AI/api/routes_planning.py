from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from export.scene_bundle import build_scene_bundle
from policy.unknown_space import apply_unknown_policy
from scaffold.bom import bom_from_elements
from scaffold.solver import generate_scaffold
from scaffold.validators import collision_check
from scanning.next_best_view import generate_scan_plan
from scanning.readiness import compute_readiness
from trace.decision_trace import add_trace_event

router = APIRouter(tags=["planning"])


@router.get("/session/{session_id}/scan_plan")
def scan_plan(request: Request, session_id: str):
    state = request.app.state.runtime
    world = state.get_world(session_id)
    anchors = state.anchors.get(session_id, [])
    return {"scan_plan": generate_scan_plan(world, anchors)}


@router.post("/session/{session_id}/request_scaffold")
def request_scaffold(request: Request, session_id: str):
    state = request.app.state.runtime
    world = state.get_world(session_id)
    anchors = state.anchors.get(session_id, [])
    ready, score, reasons = compute_readiness(world, anchors, state.policy)
    scan_plan = generate_scan_plan(world, anchors)
    if not ready:
        raise HTTPException(status_code=409, detail={"status": "NEEDS_SCAN", "reasons": reasons, "scan_plan": scan_plan, "score": score})

    elements, solver_trace = generate_scaffold(world, anchors, state.policy)
    valid, violations = collision_check(elements, world, state.policy)
    unknown = apply_unknown_policy(world, anchors, state.policy)
    violations.extend(unknown["violations"])
    if not valid or violations:
        raise HTTPException(status_code=409, detail={"status": "UNSAFE", "violations": violations})

    add_trace_event(state.traces.setdefault(session_id, []), "scaffold_generated", {"elements": len(elements)})
    state.traces[session_id].extend(solver_trace)

    overlays = world.compute_overlays(state.policy.__dict__)
    overlays["violations"] = violations

    env_mesh_bytes = world.export_env_mesh_obj()
    rev_id = state.store.lock_revision(session_id, world.serialize_state(), overlays, state.traces[session_id], env_mesh_bytes=env_mesh_bytes)
    state.last_rev[session_id] = rev_id

    sg = getattr(state, "scene_graphs", {}).get(session_id)
    bundle = build_scene_bundle(session_id, rev_id, world, anchors, elements, scan_plan, overlays, scene_graph=sg)
    bundle["bom"] = bom_from_elements(elements)
    bundle["env_mesh"]["present"] = bool(env_mesh_bytes)

    state.store.save_export(session_id, rev_id, bundle)
    return bundle
