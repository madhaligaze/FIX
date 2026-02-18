from __future__ import annotations

import time


def build_scene_bundle(session_id: str, rev_id: str, world_model, anchors, scaffold, scan_plan, overlays) -> dict:
    return {
        "session_id": session_id,
        "revision_id": rev_id,
        "timestamp": time.time(),
        "env_mesh": {"format": "obj", "path": f"sessions/{session_id}/world/{rev_id}/env_mesh.obj"},
        "objects": [],
        "scaffold": scaffold,
        "anchors": anchors,
        "overlays": overlays,
        "scan_hints": scan_plan,
        "world": world_model.serialize_state(),
    }
