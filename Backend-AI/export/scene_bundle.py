from __future__ import annotations

import time
from pathlib import Path

from export.overlays_export import export_occupancy_npz, export_occupancy_slice_png


def build_scene_bundle(
    session_id: str,
    rev_id: str,
    world_model,
    anchors,
    scaffold,
    scan_plan,
    overlays,
    scene_graph=None,
) -> dict:
    objects = []
    meta = {}
    if scene_graph is not None:
        payload = scene_graph.serialize()
        objects = payload.get("objects", [])
        meta = payload.get("meta", {})

    # STAGE 7 overlays: provide stable files for Android overlay rendering
    # These are stored under sessions/<session_id>/world/<rev_id>/...
    world_dir = Path("sessions") / session_id / "world" / rev_id
    occ_npz = export_occupancy_npz(world_model, world_dir / "occupancy.npz")
    occ_png = export_occupancy_slice_png(world_model, world_dir / "occupancy_z.png", axis="z", frac=0.2)

    return {
        "session_id": session_id,
        "revision_id": rev_id,
        "timestamp": time.time(),
        "env_mesh": {"format": "obj", "path": f"sessions/{session_id}/world/{rev_id}/env_mesh.obj"},
        "trace": {
            "format": "ndjson",
            "path": f"sessions/{session_id}/world/{rev_id}/trace.ndjson",
            "json_path": f"sessions/{session_id}/world/{rev_id}/trace.json",
        },
        "objects": objects,
        "scene_meta": meta,
        "scaffold": scaffold,
        "anchors": anchors,
        "overlays": overlays,
        "scan_hints": scan_plan,
        "world": world_model.serialize_state(),
        "overlay_files": {
            "occupancy": {"npz": {"path": str(occ_npz["path"]).replace("\\", "/")}},
            "occupancy_slice": (
                {"png": {"path": str(occ_png["path"]).replace("\\", "/")}} if occ_png else {"png": None}
            ),
        },
    }
