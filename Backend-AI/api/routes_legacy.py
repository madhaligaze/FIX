from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from api.ingest import ingest_frame
from contracts.frame_packet import FramePacketMeta
from contracts.legacy_stream import LegacyStreamPayload
from trace.decision_trace import add_trace_event

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
    result.update({"legacy_stream": True, "legacy_mode": "json_adapter"})
    return result


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
