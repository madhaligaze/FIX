from __future__ import annotations

from typing import Any

from trace.decision_trace import add_trace_event


def ingest_frame(
    runtime,
    session_id: str,
    frame_id: str,
    meta_dict: dict[str, Any],
    rgb_bytes: bytes,
    depth_bytes: bytes | None,
    pointcloud_bytes: bytes | None,
) -> dict[str, Any]:
    runtime.get_world(session_id)
    runtime.anchors.setdefault(session_id, [])
    runtime.traces.setdefault(session_id, [])
    runtime.store.save_frame(session_id, frame_id, meta_dict, rgb_bytes, depth_bytes, pointcloud_bytes)
    runtime.get_world(session_id).update_from_frame(meta_dict, rgb_bytes, depth_bytes, pointcloud_bytes)
    add_trace_event(runtime.traces[session_id], "frame_ingested", {"frame_id": frame_id})
    return {
        "status": "ok",
        "session_id": session_id,
        "frame_id": frame_id,
        "frames": runtime.get_world(session_id).metrics["frames"],
    }
