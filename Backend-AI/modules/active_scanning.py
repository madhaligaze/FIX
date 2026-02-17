"""Stage 6.2 - Active scanning plan.

Stage 6 baseline:
- Cluster scan_suggestions (3D points) and return one view per top cluster.

Stage 6.2 improvements:
- Generate multiple candidate views per cluster (azimuth offsets + distance ring).
- Score candidates with a conservative visibility model:
  * Hard penalty if line-of-sight is blocked by OCCUPIED voxels.
  * Penalty proportional to UNKNOWN density along the ray.
  * Penalty if candidate position is inside/near OCCUPIED.
- Pick the top-N diverse views across clusters.

Notes
-----
- This module avoids heavy dependencies. It uses numpy only.
- We assume ARCore-like world axis where Y is roughly "up". If your project uses
  a different convention, adjust rotation/projection helpers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import math
import numpy as np

from modules.information_gain import TargetBox, estimate_information_gain


def _vec3(p: Dict[str, Any]) -> np.ndarray:
    return np.array([float(p.get("x", 0.0)), float(p.get("y", 0.0)), float(p.get("z", 0.0))], dtype=float)


def _normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n <= 1e-9:
        return v
    return v / n


def _project_xz(v: np.ndarray) -> np.ndarray:
    return np.array([float(v[0]), 0.0, float(v[2])], dtype=float)


def _rotate_y(v: np.ndarray, angle_rad: float) -> np.ndarray:
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    x, y, z = float(v[0]), float(v[1]), float(v[2])
    return np.array([c * x + s * z, y, -s * x + c * z], dtype=float)


def _cluster_points_grid(points: List[Dict[str, Any]], cell_m: float = 0.8) -> List[Dict[str, Any]]:
    """Cluster points by coarse 3D grid."""
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
            r = str(it.get("reason", "unknown"))
            reasons[r] = reasons.get(r, 0) + 1

        clusters.append(
            {
                "center": {"x": float(center[0]), "y": float(center[1]), "z": float(center[2])},
                "count": len(items),
                "severity": severity,
                "reasons": reasons,
                "priority": float(len(items)) * (0.5 + severity),
            }
        )

    clusters.sort(key=lambda c: float(c.get("priority", 0.0)), reverse=True)
    return clusters


def _candidate_positions(
    target: np.ndarray,
    cam_pos: Optional[np.ndarray],
    distance_m: float,
    angles_deg: Tuple[float, ...],
    distance_multipliers: Tuple[float, ...],
) -> List[np.ndarray]:
    """Generate candidate camera positions on a ring around the target."""
    if cam_pos is None:
        base_dir = np.array([0.0, 0.0, -1.0], dtype=float)
        base_height = float(target[1]) + 0.2
    else:
        base_dir = cam_pos - target
        base_height = float(cam_pos[1])

    # Prefer lateral moves: project onto XZ and renormalize.
    base_dir = _project_xz(base_dir)
    if float(np.linalg.norm(base_dir)) <= 1e-6:
        base_dir = np.array([0.0, 0.0, -1.0], dtype=float)

    base_dir = _normalize(base_dir)

    candidates: List[np.ndarray] = []
    for mul in distance_multipliers:
        d = float(distance_m) * float(mul)
        for a in angles_deg:
            v = _rotate_y(base_dir, math.radians(float(a)))
            v = _normalize(_project_xz(v))
            pos = target + v * d
            pos[1] = base_height
            candidates.append(pos)

    return candidates


def _score_candidate(
    voxel_world: Any,
    pos: np.ndarray,
    target: np.ndarray,
    cluster_priority: float,
    default_distance_m: float,
    target_box: Optional[Dict[str, Any]] = None,
    gain_weight: float = 8.0,
    gain_samples: int = 220,
) -> Tuple[float, Dict[str, Any]]:
    """Compute a conservative score for a candidate view.

    Adds a Stage 7 information-gain proxy when target_box is available.
    """
    dist = float(np.linalg.norm(pos - target))
    score = float(cluster_priority)
    diag: Dict[str, Any] = {"distance_m": dist}

    # Distance penalty (keep around default).
    score -= 0.5 * abs(dist - float(default_distance_m))

    if voxel_world is None:
        diag["has_world"] = False
        return score, diag

    diag["has_world"] = True

    # Penalize if camera position is inside occupied.
    try:
        st = int(voxel_world.get_state(float(pos[0]), float(pos[1]), float(pos[2])))
        diag["pos_state"] = st
        if st == getattr(voxel_world, "OCCUPIED", 1):
            score -= 20.0
            diag["pos_penalty"] = 20.0
    except Exception:
        pass

    # Hard penalty if line-of-sight is blocked by occupied.
    blocked = False
    try:
        blocked = bool(
            voxel_world.is_blocked(
                (float(pos[0]), float(pos[1]), float(pos[2])),
                (float(target[0]), float(target[1]), float(target[2])),
                clearance=0.03,
                unknown_is_blocked=False,
            )
        )
    except Exception:
        blocked = False

    diag["los_blocked"] = blocked
    if blocked:
        score -= 10.0

    # Penalize UNKNOWN density along the segment.
    try:
        unk = float(
            voxel_world.segment_unknown_ratio(
                (float(pos[0]), float(pos[1]), float(pos[2])),
                (float(target[0]), float(target[1]), float(target[2])),
                sample_step_m=max(0.5 * float(getattr(voxel_world, "resolution", 0.1)), 0.05),
            )
        )
        diag["unknown_ratio"] = unk
        score -= 5.0 * unk
    except Exception:
        pass

    # Stage 7: Information gain proxy in the planning target region.
    if target_box:
        try:
            c = target_box.get("center") or {}
            h = target_box.get("half_extents") or target_box.get("half_extents_m") or {}
            box = TargetBox(
                center=(float(c.get("x", 0.0)), float(c.get("y", 0.0)), float(c.get("z", 0.0))),
                half_extents=(float(h.get("x", 0.0)), float(h.get("y", 0.0)), float(h.get("z", 0.0))),
            )
            gain, gdiag = estimate_information_gain(
                voxel_world=voxel_world,
                camera_pos=(float(pos[0]), float(pos[1]), float(pos[2])),
                box=box,
                max_samples=int(gain_samples),
            )
            diag["info_gain"] = float(gain)
            diag["info_gain_diag"] = gdiag
            score += float(gain_weight) * float(gain)
        except Exception:
            pass

    return score, diag


def propose_views(
    scan_suggestions: List[Dict[str, Any]],
    current_pose: Optional[List[float]],
    voxel_world: Any = None,
    target_box: Optional[Dict[str, Any]] = None,
    gain_weight: float = 8.0,
    gain_samples: int = 220,
    default_distance_m: float = 1.6,
    max_views: int = 3,
    angles_deg: Tuple[float, ...] = (0.0, 25.0, -25.0, 55.0, -55.0, 180.0),
    distance_multipliers: Tuple[float, ...] = (1.0, 1.25),
    max_clusters: int = 5,
    min_view_separation_m: float = 0.8,
) -> Dict[str, Any]:
    """Return clusters and next-best-view proposals.

    Each view includes:
    - position: {x,y,z}
    - look_at: {x,y,z}
    - reason: string
    - score: float
    - priority: float (cluster priority)
    - diagnostics: {..}

    We pick `max_views` views globally (not per-cluster) but we keep the
    cluster info in each entry.
    """
    clusters = _cluster_points_grid(scan_suggestions, cell_m=0.8)

    if angles_deg is None:
        angles_deg = (0.0, 25.0, -25.0, 55.0, -55.0, 180.0)
    if distance_multipliers is None:
        distance_multipliers = (1.0, 1.25)
    if not clusters:
        return {"clusters": [], "next_best_views": []}

    cam_pos = None
    if current_pose and len(current_pose) >= 3:
        cam_pos = np.array([float(current_pose[0]), float(current_pose[1]), float(current_pose[2])], dtype=float)

    candidates: List[Dict[str, Any]] = []

    for c in clusters[: max(1, int(max_clusters))]:
        target = _vec3(c["center"])
        cand_positions = _candidate_positions(
            target=target,
            cam_pos=cam_pos,
            distance_m=float(default_distance_m),
            angles_deg=tuple(float(a) for a in angles_deg),
            distance_multipliers=tuple(float(m) for m in distance_multipliers),
        )

        for pos in cand_positions:
            sc, diag = _score_candidate(
                voxel_world=voxel_world,
                pos=pos,
                target=target,
                cluster_priority=float(c.get("priority", 0.0)),
                default_distance_m=float(default_distance_m),
                target_box=target_box,
                gain_weight=float(gain_weight),
                gain_samples=int(gain_samples),
            )
            candidates.append(
                {
                    "position": {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])},
                    "look_at": {"x": float(target[0]), "y": float(target[1]), "z": float(target[2])},
                    "reason": "scan_cluster",
                    "score": float(sc),
                    "priority": float(c.get("priority", 0.0)),
                    "cluster": c,
                    "diagnostics": diag,
                }
            )

    # Sort by score.
    candidates.sort(key=lambda v: float(v.get("score", 0.0)), reverse=True)

    # Greedy pick diverse views.
    picked: List[Dict[str, Any]] = []
    for cand in candidates:
        if len(picked) >= int(max_views):
            break
        p = cand.get("position") or {}
        pvec = np.array([float(p.get("x", 0.0)), float(p.get("y", 0.0)), float(p.get("z", 0.0))], dtype=float)

        ok = True
        for prev in picked:
            q = prev.get("position") or {}
            qvec = np.array([float(q.get("x", 0.0)), float(q.get("y", 0.0)), float(q.get("z", 0.0))], dtype=float)
            if float(np.linalg.norm(pvec - qvec)) < float(min_view_separation_m):
                ok = False
                break
        if ok:
            picked.append(cand)

    return {"clusters": clusters, "next_best_views": picked}
