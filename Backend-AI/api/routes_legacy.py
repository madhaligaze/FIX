from __future__ import annotations

import base64
import json
import time
from typing import Any
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from api.ingest import ingest_frame
from contracts.frame_packet import FramePacketMeta
from contracts.legacy_stream import LegacyStreamPayload
from policy.unknown_space import apply_unknown_policy
from scaffold.solver import generate_scaffold
from scaffold.validators import collision_check
from scanning.next_best_view import generate_scan_plan
from scanning.readiness import compute_readiness
from trace.decision_trace import add_trace_event
from world.occupancy import OCCUPIED

router = APIRouter(tags=["legacy"])

# Android API usage audit (from ApiService.kt) for compatibility adapters:
# - POST /session/start -> expects {session_id,status} JSON.
# - POST /session/stream/{session_id} -> sends JSON map (often base64 image/depth + optional geometry fields), expects {status, ai_hints?}.
# - GET /health -> expects status/version/modules (version/modules are optional on client side).
# - GET /session/voxels/{session_id}, POST /session/model/{session_id}, POST /session/update/{session_id},
#   POST /session/preview_remove/{session_id} are also called by Android and should remain available in legacy stack.


def _decode_base64(value: str | None) -> bytes | None:
    if not value:
        return None
    try:
        return base64.b64decode(value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid base64 payload: {exc}") from exc


def _build_meta(session_id: str, payload: LegacyStreamPayload) -> tuple[dict, bytes, bytes | None, bytes | None]:
    intrinsics = payload.intrinsics or {}
    pose = payload.pose or {}

    rgb_b64 = payload.rgb_base64 or payload.image_base64 or payload.rgb
    rgb_bytes = _decode_base64(rgb_b64)
    if rgb_bytes is None:
        raise HTTPException(status_code=400, detail="Missing rgb_base64/image_base64/rgb in legacy payload")

    depth_b64 = payload.depth_base64 or payload.depth
    depth_bytes = _decode_base64(depth_b64)

    pc = payload.point_cloud or payload.pointcloud
    pointcloud_bytes = None
    pointcloud_meta = None
    if pc is not None:
        # Legacy JSON point cloud is stored as UTF-8 JSON bytes for artifact persistence, so the new pipeline
        # can track original content without assuming a binary schema.
        pointcloud_bytes = json.dumps(pc).encode("utf-8")
        pointcloud_meta = {"format": "xyz", "frame": "world"}

    missing: list[str] = []
    for key in ("fx", "fy", "cx", "cy", "width", "height"):
        if key not in intrinsics:
            missing.append(f"intrinsics.{key}")
    if "position" not in pose:
        missing.append("pose.position")
    if "quaternion" not in pose:
        missing.append("pose.quaternion")
    if depth_bytes is None and pointcloud_bytes is None:
        missing.append("depth_base64|point_cloud")
    if missing:
        raise HTTPException(
            status_code=409,
            detail={
                "status": "NEEDS_GEOMETRY",
                "missing": missing,
                "hint": "Use /session/frame contract or send intrinsics+pose+size",
            },
        )

    depth_meta = None
    if depth_bytes is not None:
        depth_meta = {
            "width": int(payload.depth_width or intrinsics["width"]),
            "height": int(payload.depth_height or intrinsics["height"]),
            "scale_m_per_unit": float(payload.depth_scale or 0.001),
            "encoding": "uint16",
        }

    frame_id = payload.frame_id or str(uuid4())
    meta_dict = {
        "session_id": session_id,
        "frame_id": frame_id,
        "timestamp": float(payload.timestamp or time.time()),
        "intrinsics": intrinsics,
        "pose": pose,
        "depth_meta": depth_meta,
        "pointcloud_meta": pointcloud_meta,
    }

    # Validate adapter output against canonical FramePacket schema before ingesting.
    FramePacketMeta.model_validate(meta_dict)
    return meta_dict, rgb_bytes, depth_bytes, pointcloud_bytes


@router.post("/session/start")
def legacy_start_session(request: Request):
    state = request.app.state.runtime
    session_id = state.store.create_session()
    state.get_world(session_id)
    state.anchors[session_id] = []
    state.traces[session_id] = []
    return {"session_id": session_id, "status": "ok"}


@router.post("/session/stream")
def legacy_stream(request: Request, payload: LegacyStreamPayload):
    session_id = payload.session_id
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required for /session/stream")
    return _legacy_stream_ingest(request, session_id, payload)


@router.post("/session/stream/{session_id}")
def legacy_stream_with_path(request: Request, session_id: str, payload: LegacyStreamPayload):
    return _legacy_stream_ingest(request, session_id, payload)


def _legacy_stream_ingest(request: Request, session_id: str, payload: LegacyStreamPayload):
    state = request.app.state.runtime
    meta_dict, rgb_bytes, depth_bytes, pointcloud_bytes = _build_meta(session_id, payload)
    result = ingest_frame(
        state,
        session_id,
        meta_dict["frame_id"],
        meta_dict,
        rgb_bytes,
        depth_bytes,
        pointcloud_bytes,
    )
    world = state.get_world(session_id)
    anchors = state.anchors.get(session_id, [])
    ready, score, reasons = compute_readiness(world, anchors, state.policy)
    numeric_score = float(score) if isinstance(score, (int, float)) else 0.0
    quality_score = numeric_score * 100.0 if 0.0 <= numeric_score <= 1.0 else numeric_score
    quality_score = max(0.0, min(100.0, quality_score))

    if ready:
        instructions = ["Можно моделировать."]
    else:
        scan_plan = generate_scan_plan(world, anchors)
        instructions = []
        for item in scan_plan[:3]:
            note = item.get("note")
            instructions.append(f"Досканируйте: {note}" if note else "Сделайте обзор вокруг точки опоры")

    result.update(
        {
            "status": "RECEIVING",
            "ai_hints": {
                "instructions": instructions,
                "warnings": [str(reason) for reason in reasons],
                "quality_score": quality_score,
                "is_ready": bool(ready),
            },
            "legacy_stream": True,
            "legacy_mode": "json_adapter",
        }
    )
    return result


def _load_latest_export(state, session_id: str) -> dict[str, Any] | None:
    rev_id = state.last_rev.get(session_id)
    if not rev_id:
        latest_path = state.store.session_root(session_id) / "exports" / "latest.json"
        if latest_path.exists():
            rev_id = json.loads(latest_path.read_text(encoding="utf-8")).get("rev_id")
    if not rev_id:
        return None
    try:
        return state.store.load_export(session_id, rev_id)
    except FileNotFoundError:
        return None


def _legacy_element_to_android(element: dict[str, Any]) -> dict[str, Any]:
    if "start" in element and "end" in element:
        start = element.get("start") or [0.0, 0.0, 0.0]
        end = element.get("end") or [0.0, 0.0, 0.0]
    else:
        pos = (((element.get("pose") or {}).get("pos")) or [0.0, 0.0, 0.0])
        dims = element.get("dims") or {}
        length_x = float(dims.get("x", 0.0) or 0.0)
        length_y = float(dims.get("y", 0.0) or 0.0)
        length_z = float(dims.get("z", 0.0) or 0.0)
        axis = max([(length_x, 0), (length_y, 1), (length_z, 2)], key=lambda x: x[0])[1]
        half = [0.0, 0.0, 0.0]
        half[axis] = max(length_x, length_y, length_z) / 2.0
        start = [float(pos[0] - half[0]), float(pos[1] - half[1]), float(pos[2] - half[2])]
        end = [float(pos[0] + half[0]), float(pos[1] + half[1]), float(pos[2] + half[2])]

    return {
        "id": str(element.get("id", "")),
        "type": str(element.get("type", "beam")),
        "start": [float(start[0]), float(start[1]), float(start[2])],
        "end": [float(end[0]), float(end[1]), float(end[2])],
        "meta": element.get("meta") or {},
    }


@router.get("/session/voxels/{session_id}")
def legacy_voxels(request: Request, session_id: str):
    state = request.app.state.runtime
    world = state.get_world(session_id)
    occupancy = world.occupancy
    grid = occupancy.grid
    max_emit = 20000

    occupied_idx = (grid == OCCUPIED).nonzero()
    occupied_positions = list(zip(occupied_idx[0], occupied_idx[1], occupied_idx[2]))
    total_count = len(occupied_positions)
    emitted = occupied_positions[:max_emit]

    voxels = []
    for x_i, y_i, z_i in emitted:
        pos = [
            float(occupancy.origin[0] + occupancy.voxel_size * float(x_i)),
            float(occupancy.origin[1] + occupancy.voxel_size * float(y_i)),
            float(occupancy.origin[2] + occupancy.voxel_size * float(z_i)),
        ]
        voxels.append(
            {
                "position": [float(pos[0]), float(pos[1]), float(pos[2])],
                "type": "occupied",
                "color": "#D94A4A",
                "alpha": 0.9,
                "radius": None,
            }
        )

    shape = grid.shape
    bounds_min = occupancy.origin
    bounds_max = [
        float(occupancy.origin[0] + occupancy.voxel_size * float(shape[0])),
        float(occupancy.origin[1] + occupancy.voxel_size * float(shape[1])),
        float(occupancy.origin[2] + occupancy.voxel_size * float(shape[2])),
    ]
    return {
        "status": "ok",
        "voxels": voxels,
        "bounds": {
            "min": [float(bounds_min[0]), float(bounds_min[1]), float(bounds_min[2])],
            "max": [float(bounds_max[0]), float(bounds_max[1]), float(bounds_max[2])],
        },
        "resolution": float(occupancy.voxel_size),
        "total_count": int(total_count),
    }


@router.post("/session/model/{session_id}")
def legacy_model(request: Request, session_id: str):
    state = request.app.state.runtime
    world = state.get_world(session_id)
    anchors = state.anchors.get(session_id, [])
    ready, score, reasons = compute_readiness(world, anchors, state.policy)

    if not ready:
        return {
            "status": "NEEDS_SCAN",
            "options": [
                {
                    "variant_name": "Scan required",
                    "material_info": "",
                    "safety_score": 0,
                    "ai_critique": [str(reason) for reason in reasons],
                    "elements": [],
                    "full_structure": {"elements": []},
                    "stats": {
                        "total_nodes": 0,
                        "total_beams": 0,
                        "total_weight_kg": 0,
                        "collisions_fixed": 0,
                    },
                    "physics": {"status": "ERROR"},
                }
            ],
        }

    try:
        elements, _trace = generate_scaffold(world, anchors, state.policy)
        valid, violations = collision_check(elements, world, state.policy)
        unknown = apply_unknown_policy(world, anchors, state.policy)
        violations.extend(unknown["violations"])
        if not valid:
            violations.append("SCHEMA_OR_COLLISION_INVALID")

        score_norm = float(score) if isinstance(score, (int, float)) else 0.0
        score_norm = score_norm / 100.0 if score_norm > 1.0 else score_norm
        safety_score = max(0, min(100, int(score_norm * 100) - 10 * len(violations)))
        android_elements = [_legacy_element_to_android(el) for el in elements]
        unique_nodes = {tuple(e["start"]) for e in android_elements} | {tuple(e["end"]) for e in android_elements}
        return {
            "status": "ok",
            "options": [
                {
                    "variant_name": "Auto",
                    "material_info": "LAYHER",
                    "safety_score": safety_score,
                    "ai_critique": [str(v) for v in violations],
                    "elements": android_elements,
                    "full_structure": {"elements": android_elements},
                    "stats": {
                        "total_nodes": len(unique_nodes),
                        "total_beams": len(android_elements),
                        "total_weight_kg": 0,
                        "collisions_fixed": 0,
                    },
                    "physics": {"status": "OK"},
                }
            ],
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "options": [
                {
                    "variant_name": "Auto",
                    "material_info": "",
                    "safety_score": 0,
                    "ai_critique": [f"MODEL_ADAPTER_ERROR: {exc}"],
                    "elements": [],
                    "full_structure": {"elements": []},
                    "stats": {
                        "total_nodes": 0,
                        "total_beams": 0,
                        "total_weight_kg": 0,
                        "collisions_fixed": 0,
                    },
                    "physics": {"status": "ERROR"},
                }
            ],
        }


@router.post("/session/update/{session_id}")
def legacy_update(request: Request, session_id: str, payload: dict[str, Any] | None = None):
    state = request.app.state.runtime
    started = time.perf_counter()
    _ = _load_latest_export(state, session_id)
    action_payload = payload or {}
    state.traces.setdefault(session_id, [])
    add_trace_event(state.traces[session_id], "legacy_update_noop", {"session_id": session_id, "action": action_payload})
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "status": "ok",
        "is_stable": True,
        "physics_status": "OK",
        "heatmap": [],
        "affected_elements": [],
        "collapsed": {"nodes": [], "elements": []},
        "processing_time_ms": elapsed_ms,
    }


@router.post("/session/preview_remove/{session_id}")
def legacy_preview_remove(request: Request, session_id: str, element_id: str | None = None):
    state = request.app.state.runtime
    export_bundle = _load_latest_export(state, session_id) or {}
    scaffold = export_bundle.get("scaffold") or []
    found = False
    if element_id:
        found = any(str(item.get("id")) == str(element_id) for item in scaffold if isinstance(item, dict))

    return {
        "status": "ok",
        "element_id": element_id,
        "is_critical": False,
        "would_collapse": [],
        "collapse_count": 0,
        "warning": "" if found else "element not found",
    }


@router.post("/session/unlock/{session_id}")
def legacy_unlock(request: Request, session_id: str):
    state = request.app.state.runtime
    state.last_rev.pop(session_id, None)
    state.traces.setdefault(session_id, [])
    add_trace_event(state.traces[session_id], "legacy_unlock_noop", {"session_id": session_id})
    return {"status": "ok", "noop": True}


@router.get("/session/snapshots/{session_id}")
def legacy_snapshots(request: Request, session_id: str):
    state = request.app.state.runtime
    world_dir = state.store.session_root(session_id) / "world"
    export_dir = state.store.session_root(session_id) / "exports"
    revisions = []
    if world_dir.exists():
        for p in sorted([d for d in world_dir.iterdir() if d.is_dir()], key=lambda x: x.name):
            revisions.append({"revision": p.name, "has_world_state": (p / "world_state.json").exists()})
    latest = None
    latest_file = export_dir / "latest.json"
    if latest_file.exists():
        latest = json.loads(latest_file.read_text(encoding="utf-8")).get("rev_id")
    return {"status": "ok", "session_id": session_id, "snapshots": revisions, "latest_revision": latest}


@router.post("/session/snapshot/restore/{session_id}/{revision}")
def legacy_restore_snapshot(request: Request, session_id: str, revision: str):
    state = request.app.state.runtime
    base = state.store.session_root(session_id) / "world" / revision
    world_state_path = base / "world_state.json"
    overlays_path = base / "overlays.json"
    trace_path = base / "trace.json"
    if not world_state_path.exists():
        raise HTTPException(status_code=404, detail=f"Revision not found: {revision}")

    world_state = json.loads(world_state_path.read_text(encoding="utf-8"))
    overlays = json.loads(overlays_path.read_text(encoding="utf-8")) if overlays_path.exists() else {}
    traces = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else []

    state.last_rev[session_id] = revision
    state.traces[session_id] = traces
    state.restored_revision_state[session_id] = {
        "revision": revision,
        "world_state": world_state,
        "overlays": overlays,
    }
    return {"status": "ok", "session_id": session_id, "revision": revision, "restored": True}
