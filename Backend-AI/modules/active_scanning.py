"""Stage 6 - Active scanning plan.

Takes raw scan_suggestions (world-space points) and converts them into a
small set of actionable view proposals for the Android operator.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def _vec3(p: Dict[str, Any]) -> np.ndarray:
    return np.array([float(p.get("x", 0.0)), float(p.get("y", 0.0)), float(p.get("z", 0.0))], dtype=float)


def _normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n <= 1e-9:
        return v
    return v / n


def _cluster_points_grid(points: List[Dict[str, Any]], cell_m: float = 0.8) -> List[Dict[str, Any]]:
    if not points:
        return []

    buckets: Dict[Tuple[int, int, int], List[Dict[str, Any]]] = {}
    for s in points:
        p = s.get("point") or s
        if not isinstance(p, dict):
            continue
        x, y, z = float(p.get("x", 0.0)), float(p.get("y", 0.0)), float(p.get("z", 0.0))
        key = (int(math.floor(x / cell_m)), int(math.floor(y / cell_m)), int(math.floor(z / cell_m)))
        buckets.setdefault(key, []).append(s)

    clusters: List[Dict[str, Any]] = []
    for items in buckets.values():
        pts = np.stack([_vec3((it.get("point") or it)) for it in items], axis=0)
        center = np.mean(pts, axis=0)
        severity = float(np.mean([float(it.get("severity", 0.5)) for it in items]))
        reasons: Dict[str, int] = {}
        for it in items:
            reason = str(it.get("reason", "unknown"))
            reasons[reason] = reasons.get(reason, 0) + 1
        clusters.append(
            {
                "center": {"x": float(center[0]), "y": float(center[1]), "z": float(center[2])},
                "count": len(items),
                "severity": float(severity),
                "reasons": reasons,
                "priority": float(len(items)) * (0.5 + severity),
            }
        )

    clusters.sort(key=lambda c: c.get("priority", 0.0), reverse=True)
    return clusters


def propose_views(
    scan_suggestions: List[Dict[str, Any]],
    current_pose: Optional[List[float]],
    default_distance_m: float = 1.6,
    max_views: int = 3,
) -> Dict[str, Any]:
    clusters = _cluster_points_grid(scan_suggestions, cell_m=0.8)
    if not clusters:
        return {"clusters": [], "next_best_views": []}

    cam_pos = None
    if current_pose and len(current_pose) >= 3:
        cam_pos = np.array([float(current_pose[0]), float(current_pose[1]), float(current_pose[2])], dtype=float)

    views: List[Dict[str, Any]] = []
    for c in clusters[: max(1, int(max_views))]:
        target = _vec3(c["center"])
        if cam_pos is None:
            cam_dir = np.array([0.0, 0.0, -1.0], dtype=float)
        else:
            cam_dir = cam_pos - target
            if float(np.linalg.norm(cam_dir)) <= 1e-6:
                cam_dir = np.array([0.0, 0.0, -1.0], dtype=float)

        cam_dir = _normalize(cam_dir)
        pos = target + cam_dir * float(default_distance_m)
        views.append(
            {
                "position": {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])},
                "look_at": {"x": float(target[0]), "y": float(target[1]), "z": float(target[2])},
                "reason": "scan_cluster",
                "priority": float(c.get("priority", 0.0)),
                "cluster": c,
            }
        )

    return {"clusters": clusters, "next_best_views": views}
