from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from export.scene_bundle import build_scene_bundle
from policy.unknown_space import apply_unknown_policy
from scaffold.bom import bom_from_elements
from scaffold.solver import generate_scaffold
from scaffold.validators import validate_all
from scanning.next_best_view import generate_scan_plan
from scanning.readiness import compute_readiness
from trace.decision_trace import add_trace_event

router = APIRouter(tags=["planning"])


@router.get("/session/{session_id}/scan_plan")
def scan_plan(request: Request, session_id: str):
    state = request.app.state.runtime
    world = state.get_world(session_id)
    anchors = state.anchors.get(session_id, [])
    sg = state.get_scene_graph(session_id)
    needs_scan = (sg.meta or {}).get("needs_scan", [])

    plan = generate_scan_plan(world, anchors)
    if needs_scan:
        plan = list(needs_scan) + list(plan)
    return {"scan_plan": plan}


@router.post("/session/{session_id}/request_scaffold")
def request_scaffold(request: Request, session_id: str):
    state = request.app.state.runtime
    world = state.get_world(session_id)
    anchors = state.anchors.get(session_id, [])

    ready, score, reasons = compute_readiness(world, anchors, state.policy)
    scan_plan = generate_scan_plan(world, anchors)

    sg = state.get_scene_graph(session_id)
    needs_scan = (sg.meta or {}).get("needs_scan", [])
    if needs_scan:
        scan_plan = list(needs_scan) + list(scan_plan)

    if not ready:
        raise HTTPException(
            status_code=409,
            detail={"status": "NEEDS_SCAN", "reasons": reasons, "scan_plan": scan_plan, "score": score},
        )

    elements, solver_trace = generate_scaffold(world, anchors, state.policy)

    valid, violations = validate_all(elements, world, state.policy)
    unknown = apply_unknown_policy(world, anchors, state.policy)
    violations.extend(unknown["violations"])

    add_trace_event(state.traces.setdefault(session_id, []), "scaffold_generated", {"elements": len(elements)})
    state.traces[session_id].extend(solver_trace)

    if (not valid or violations) and bool(getattr(state.policy, "enforce_validators_strict", True)):
        add_trace_event(state.traces[session_id], "scaffold_blocked", {"violations": violations}, level="warn")
        raise HTTPException(status_code=409, detail={"status": "UNSAFE", "violations": violations})

    overlays = world.compute_overlays(state.policy.__dict__)
    overlays["violations"] = violations

    env_mesh_bytes = world.export_env_mesh_obj()
    rev_id = state.store.lock_revision(
        session_id,
        world.serialize_state(),
        overlays,
        state.traces[session_id],
        env_mesh_bytes=env_mesh_bytes,
    )
    state.last_rev[session_id] = rev_id

    bundle = build_scene_bundle(session_id, rev_id, world, anchors, elements, scan_plan, overlays, scene_graph=sg)
    bundle["bom"] = bom_from_elements(elements)
    bundle["env_mesh"]["present"] = bool(env_mesh_bytes)
    bundle["trace"]["present"] = True
    bundle["trace"]["ndjson_size_bytes"] = None  # filled by client if needed
    # Keep paths normalized for Android clients on Windows-hosted servers
    if "overlay_files" in bundle:
        # already normalized in build_scene_bundle
        pass

    state.store.save_export(session_id, rev_id, bundle)
    return bundle
