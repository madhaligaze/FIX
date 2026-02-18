from __future__ import annotations

from scaffold.spec import LAYHER_SPEC


def generate_scaffold(world_model, anchors: list[dict], policy) -> tuple[list[dict], list[dict]]:
    trace = [{"event": "solver_start", "anchors": len(anchors)}]
    supports = [a for a in anchors if a.get("kind") in {"support", "target", "boundary"}]
    if not supports:
        supports = [
            {"id": "default-0", "position": [0.0, 0.0, 0.0]},
            {"id": "default-1", "position": [2.0, 0.0, 0.0]},
            {"id": "default-2", "position": [2.0, 2.0, 0.0]},
            {"id": "default-3", "position": [0.0, 2.0, 0.0]},
        ]

    elements = []
    for idx, s in enumerate(supports[:4]):
        elements.append(
            {
                "id": f"post-{idx}",
                "type": "post",
                "pose": {"pos": s["position"], "quat": [0, 0, 0, 1]},
                "dims": {"x": 0.05, "y": 0.05, "z": LAYHER_SPEC["post_default_height_m"]},
                "meta": {"length_m": LAYHER_SPEC["post_default_height_m"]},
            }
        )
    trace.append({"event": "solver_done", "elements": len(elements)})
    return elements, trace
