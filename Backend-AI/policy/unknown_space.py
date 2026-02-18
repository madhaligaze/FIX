from __future__ import annotations

from typing import Any

import numpy as np

from world.occupancy import UNKNOWN


def _as3(p: Any) -> np.ndarray | None:
    if isinstance(p, (list, tuple)) and len(p) == 3:
        return np.asarray(p, dtype=np.float32).reshape(3)
    return None


def _nearby_unknown(world_model, point_w: np.ndarray, radius_m: float) -> bool:
    """
    Approximate 'distance to unknown' by scanning a voxel cube around the point.
    Conservative: if any unknown voxel exists in radius, return True.
    """
    occ = world_model.occupancy
    r = float(max(0.0, radius_m))
    if r <= 1e-6:
        v = int(occ.query([point_w.tolist()])[0])
        return v == int(UNKNOWN)

    center = ((point_w - occ.origin) / float(occ.voxel_size)).astype(np.int32)
    dr = int(np.ceil(r / float(occ.voxel_size)))
    i0 = np.maximum(center - dr, 0)
    i1 = np.minimum(center + dr + 1, np.asarray(occ.grid.shape, dtype=np.int32))
    if np.any(i1 <= i0):
        return True

    sub = occ.grid[i0[0] : i1[0], i0[1] : i1[1], i0[2] : i1[2]]
    return bool(np.any(sub == UNKNOWN))


def check_points_against_unknown(
    world_model,
    points: list[list[float]],
    *,
    mode: str,
    buffer_m: float,
) -> list[dict[str, Any]]:
    mode = str(mode or "forbid").strip().lower()
    buf = float(max(0.0, buffer_m))
    if mode == "allow":
        return []

    violations: list[dict[str, Any]] = []
    for i, p in enumerate(points):
        pw = _as3(p)
        if pw is None:
            continue

        inside_unknown = _nearby_unknown(world_model, pw, radius_m=0.0)
        near_unknown = _nearby_unknown(world_model, pw, radius_m=buf) if buf > 0 else inside_unknown

        if mode == "forbid":
            if inside_unknown:
                violations.append({"type": "UNKNOWN_FORBIDDEN", "index": i, "point": p, "mode": mode})
            elif buf > 0 and near_unknown:
                violations.append(
                    {
                        "type": "UNKNOWN_BUFFER_FORBIDDEN",
                        "index": i,
                        "point": p,
                        "buffer_m": buf,
                        "mode": mode,
                    }
                )
        elif mode == "buffer":
            if (buf > 0 and near_unknown) or inside_unknown:
                violations.append(
                    {
                        "type": "UNKNOWN_BUFFER_VIOLATION",
                        "index": i,
                        "point": p,
                        "buffer_m": buf,
                        "mode": mode,
                    }
                )
        else:
            if inside_unknown:
                violations.append({"type": "UNKNOWN_FORBIDDEN", "index": i, "point": p, "mode": "forbid"})
            elif buf > 0 and near_unknown:
                violations.append(
                    {
                        "type": "UNKNOWN_BUFFER_FORBIDDEN",
                        "index": i,
                        "point": p,
                        "buffer_m": buf,
                        "mode": "forbid",
                    }
                )

    return violations


def _unknown_ratio(stats: dict[str, Any]) -> float:
    try:
        u = float(stats.get("unknown", 0.0))
        t = float(stats.get("total", 0.0))
        if t <= 0.0:
            return 1.0
        return max(0.0, min(1.0, u / t))
    except Exception:
        return 1.0


def apply_unknown_policy(world_model, anchors: list[dict], policy) -> dict[str, Any]:
    """
    STAGE 8: Unknown-space as first-class policy.
    Returns a structured report + violations for gating.
    """
    mode = str(getattr(policy, "unknown_mode", "forbid")).strip().lower()
    buffer_m = float(getattr(policy, "unknown_buffer_m", 0.5))

    violations: list[dict[str, Any]] = []

    supports = [a for a in anchors if a.get("kind") == "support" and a.get("position") is not None]
    support_pts = [a["position"] for a in supports]
    if support_pts and mode != "allow":
        v = check_points_against_unknown(world_model, support_pts, mode=mode, buffer_m=buffer_m)
        for item in v:
            item["scope"] = "support"
        violations.extend(v)

    boundaries = [a for a in anchors if a.get("kind") == "boundary" and a.get("position") is not None]
    boundary_pts = [a["position"] for a in boundaries]
    if boundary_pts and mode in ("forbid", "buffer"):
        v2 = check_points_against_unknown(world_model, boundary_pts, mode="buffer", buffer_m=buffer_m)
        for item in v2:
            item["scope"] = "boundary"
        violations.extend(v2)

    unknown_summary = world_model.occupancy.stats(support_pts if support_pts else None)
    near_ratio = _unknown_ratio(unknown_summary)

    if mode == "forbid" and support_pts and near_ratio > float(getattr(policy, "unknown_ratio_near_support_max", 0.6)):
        violations.append(
            {
                "type": "UNKNOWN_NEAR_SUPPORT",
                "scope": "support",
                "unknown_ratio": float(near_ratio),
                "max_allowed": float(getattr(policy, "unknown_ratio_near_support_max", 0.6)),
            }
        )

    return {
        "mode": mode,
        "buffer_m": buffer_m,
        "forbidden_regions": [
            {"type": "sphere", "center": p, "radius": buffer_m}
            for p in support_pts
            if mode in {"forbid", "buffer"}
        ],
        "violations": violations,
        "unknown_summary": unknown_summary,
        "unknown_ratio_near_support": float(near_ratio),
        "counts": {
            "supports": int(len(support_pts)),
            "boundaries": int(len(boundary_pts)),
            "violations": int(len(violations)),
        },
    }
