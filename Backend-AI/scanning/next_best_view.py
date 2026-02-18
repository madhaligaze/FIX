from __future__ import annotations

import math
import numpy as np

from scanning.coverage import compute_unknown_hotspots, compute_work_aabb
from scanning.scan_hints import make_scan_hint


def _orbit(center: list[float], radius: float, height: float, k: int, n: int) -> dict:
    angle = (2.0 * math.pi * float(k)) / max(1.0, float(n))
    return {
        "position": [float(center[0] + radius * math.cos(angle)), float(center[1] + radius * math.sin(angle)), float(center[2] + height)],
        "look_at": [float(center[0]), float(center[1]), float(center[2])],
        "distance_m": float(radius),
        "note": "Orbit for coverage",
        "kind": "scan_hint",
    }


def generate_scan_plan(world_model, anchors: list[dict], N: int = 7) -> list[dict]:
    """
    STAGE 5: Next-best-view suggestions:
      1) If we have anchors -> focus inside work AABB and unknown hotspots.
      2) Otherwise -> generic broad context shot.
    Output is a list of scan_hint dicts (position/look_at).
    """
    supports = [a for a in anchors if a.get("kind") == "support" and a.get("position") is not None]
    work = compute_work_aabb(anchors, padding_m=1.25)

    if not supports and not work:
        return [
            make_scan_hint([1.5, 1.5, 1.6], look_at=[0.0, 0.0, 1.0], note="Capture broad context around work area")
        ]

    out: list[dict] = []

    # 1) Orbit around average of supports (stable initial coverage)
    if supports:
        P = np.asarray([s["position"] for s in supports], dtype=np.float32)
        center = np.mean(P, axis=0).tolist()
        radius = 1.8
        for k in range(min(4, max(1, N // 2))):
            out.append(_orbit(center, radius=radius, height=1.2, k=k, n=min(4, max(1, N // 2))))

    # 2) Hotspots inside work region
    if work:
        box_min, box_max = work
        hotspots = compute_unknown_hotspots(world_model, box_min, box_max, max_points=12)
        # Turn hotspots into hints: step back from hotspot and look at it
        for hp in hotspots[: max(1, N - len(out))]:
            # push camera slightly away in XY, keep height ~1.6
            look = hp
            pos = [float(hp[0] + 0.8), float(hp[1] + 0.8), float(hp[2] + 1.2)]
            out.append(make_scan_hint(pos, look_at=look, note="Scan UNKNOWN hotspot to increase confidence"))

    # Deduplicate by position distance
    dedup: list[dict] = []
    for h in out:
        p = np.asarray(h["position"], dtype=np.float32)
        if any(float(np.linalg.norm(p - np.asarray(x["position"], dtype=np.float32))) < 0.35 for x in dedup):
            continue
        dedup.append(h)
        if len(dedup) >= int(N):
            break
    return dedup
