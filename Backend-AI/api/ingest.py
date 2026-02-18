from __future__ import annotations

from typing import Any

from perception.scene_graph import update_scene_graph_from_world
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
    runtime.get_scene_graph(session_id)
    runtime.anchors.setdefault(session_id, [])
    runtime.traces.setdefault(session_id, [])

    runtime.store.save_frame(session_id, frame_id, meta_dict, rgb_bytes, depth_bytes, pointcloud_bytes)
    world = runtime.get_world(session_id)
    world.update_from_frame(meta_dict, rgb_bytes, depth_bytes, pointcloud_bytes)

    add_trace_event(runtime.traces[session_id], "frame_ingested", {"frame_id": frame_id})

    # STAGE 3 (MVP): infer dominant plane from occupancy and store in scene graph.
    sg = runtime.get_scene_graph(session_id)
    fit = update_scene_graph_from_world(sg, world, every_n_frames=5)
    if fit:
        add_trace_event(runtime.traces[session_id], "scene_graph_plane_updated", {"plane_id": "plane_dominant_0", **fit})

    return {
        "status": "ok",
        "session_id": session_id,
        "frame_id": frame_id,
        "frames": world.metrics["frames"],
        "scene_graph_objects": len(sg.objects),
    }
