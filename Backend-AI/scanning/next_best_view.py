from __future__ import annotations

import math


def generate_scan_plan(world_model, anchors: list[dict], N: int = 5) -> list[dict]:
    supports = [a for a in anchors if a.get("kind") == "support"]
    if not supports:
        return [
            {
                "position": [1.5, 1.5, 1.6],
                "look_at": [0.0, 0.0, 1.0],
                "distance_m": 2.0,
                "note": "Capture broad context around work area",
            }
        ]

    out = []
    for i, support in enumerate(supports[:N]):
        angle = (2 * math.pi * i) / max(1, min(len(supports), N))
        radius = 1.8
        center = support["position"]
        out.append(
            {
                "position": [center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle), center[2] + 1.0],
                "look_at": center,
                "distance_m": radius,
                "note": f"Orbit support {support['id']} for coverage",
            }
        )
    return out
