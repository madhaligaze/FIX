"""Stage 5: Reprojection consistency checks (no-NeRF, voxel-based).

Goal
----
Given an incoming depth frame and the current world model (VoxelWorld),
estimate whether the model matches what the camera sees.

This is NOT photogrammetry. It's a safety-oriented validator:
- if the model is inconsistent, do not "pretend" the world is known.
- produce actionable scan suggestions.

Implementation
--------------
We approximate expected depth by raycasting into OCCUPIED voxels.
UNKNOWN is tracked separately (if the ray crosses lots of UNKNOWN, we lower trust).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np


@dataclass
class ReprojectionReport:
    samples: int
    hit_rate: float
    miss_rate: float
    median_abs_error_m: float
    p90_abs_error_m: float
    unknown_ray_frac: float
    inconsistent: bool
    suggestions: List[Dict[str, float]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "samples": int(self.samples),
            "hit_rate": float(self.hit_rate),
            "miss_rate": float(self.miss_rate),
            "median_abs_error_m": float(self.median_abs_error_m),
            "p90_abs_error_m": float(self.p90_abs_error_m),
            "unknown_ray_frac": float(self.unknown_ray_frac),
            "inconsistent": bool(self.inconsistent),
            "suggestions": list(self.suggestions),
        }


def _quat_to_rotation(qx: float, qy: float, qz: float, qw: float) -> np.ndarray:
    return np.array(
        [
            [1 - 2 * (qy**2 + qz**2), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
            [2 * (qx * qy + qz * qw), 1 - 2 * (qx**2 + qz**2), 2 * (qy * qz - qx * qw)],
            [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx**2 + qy**2)],
        ],
        dtype=np.float64,
    )


def check_reprojection(
    *,
    voxel_world,
    depth_m: np.ndarray,
    width: int,
    height: int,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    pose7: List[float],
    max_depth: float = 8.0,
    pixel_step: int = 12,
    unknown_sample_step: int = 4,
    error_threshold_m: float = 0.25,
    miss_rate_threshold: float = 0.35,
) -> ReprojectionReport:
    """Compute reprojection consistency.

    Parameters
    ----------
    voxel_world : VoxelWorld
        Must implement raycast_distance() and get_state().
    depth_m : (H,W) float32
        Depth in meters. Values <=0 are invalid.
    pixel_step : int
        Sampling stride (bigger = faster, less accurate).

    Returns
    -------
    ReprojectionReport
    """
    if voxel_world is None or depth_m is None or depth_m.ndim != 2:
        return ReprojectionReport(
            samples=0,
            hit_rate=0.0,
            miss_rate=1.0,
            median_abs_error_m=0.0,
            p90_abs_error_m=0.0,
            unknown_ray_frac=1.0,
            inconsistent=True,
            suggestions=[],
        )

    if len(pose7) < 7:
        return ReprojectionReport(
            samples=0,
            hit_rate=0.0,
            miss_rate=1.0,
            median_abs_error_m=0.0,
            p90_abs_error_m=0.0,
            unknown_ray_frac=1.0,
            inconsistent=True,
            suggestions=[],
        )

    tx, ty, tz, qx, qy, qz, qw = [float(x) for x in pose7[:7]]
    rotation = _quat_to_rotation(qx, qy, qz, qw)
    camera = np.array([tx, ty, tz], dtype=np.float64)

    abs_errors: List[float] = []
    hits = 0
    misses = 0
    suggestions: List[Dict[str, float]] = []

    unknown_rays = 0
    total_rays = 0

    img_h, img_w = int(height), int(width)
    step = max(1, int(pixel_step))

    for v in range(0, img_h, step):
        for u in range(0, img_w, step):
            depth = float(depth_m[v, u])
            if depth <= 0.0 or depth > float(max_depth):
                continue

            x_cam = (float(u) - float(cx)) / float(fx)
            y_cam = (float(v) - float(cy)) / float(fy)
            dir_cam = np.array([x_cam, y_cam, 1.0], dtype=np.float64)
            dir_cam /= max(1e-9, float(np.linalg.norm(dir_cam)))

            dir_world = rotation @ dir_cam

            total_rays += 1
            unknown_count = 0
            n_samples = max(2, int(depth / max(voxel_world.resolution * unknown_sample_step, 0.2)))
            for i in range(1, n_samples):
                t = (float(i) / float(n_samples)) * depth
                point = camera + dir_world * t
                if voxel_world.get_state(float(point[0]), float(point[1]), float(point[2])) == voxel_world.UNKNOWN:
                    unknown_count += 1
            if unknown_count > 0:
                unknown_rays += 1

            predicted = voxel_world.raycast_distance(
                origin_world=(float(camera[0]), float(camera[1]), float(camera[2])),
                direction_world=(float(dir_world[0]), float(dir_world[1]), float(dir_world[2])),
                max_dist=float(max_depth),
            )

            if predicted is None:
                misses += 1
                point_world = camera + dir_world * depth
                suggestions.append(
                    {
                        "x": float(point_world[0]),
                        "y": float(point_world[1]),
                        "z": float(point_world[2]),
                        "reason": "model_missing",
                    }
                )
                continue

            hits += 1
            error = abs(float(predicted) - depth)
            abs_errors.append(error)
            if error > float(error_threshold_m):
                point_world = camera + dir_world * depth
                suggestions.append(
                    {
                        "x": float(point_world[0]),
                        "y": float(point_world[1]),
                        "z": float(point_world[2]),
                        "reason": "depth_mismatch",
                    }
                )

    samples = hits + misses
    if samples <= 0:
        return ReprojectionReport(
            samples=0,
            hit_rate=0.0,
            miss_rate=1.0,
            median_abs_error_m=0.0,
            p90_abs_error_m=0.0,
            unknown_ray_frac=1.0,
            inconsistent=True,
            suggestions=[],
        )

    if abs_errors:
        errors = np.array(abs_errors, dtype=np.float64)
        med = float(np.median(errors))
        p90 = float(np.percentile(errors, 90))
    else:
        med = 0.0
        p90 = 0.0

    hit_rate = float(hits) / float(samples)
    miss_rate = float(misses) / float(samples)
    unknown_frac = float(unknown_rays) / float(max(1, total_rays))

    inconsistent = (med > float(error_threshold_m)) or (miss_rate > float(miss_rate_threshold))

    out_suggestions: List[Dict[str, float]] = []
    seen = set()
    for suggestion in suggestions:
        key = (
            round(suggestion["x"], 2),
            round(suggestion["y"], 2),
            round(suggestion["z"], 2),
            suggestion.get("reason", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out_suggestions.append(suggestion)
        if len(out_suggestions) >= 25:
            break

    return ReprojectionReport(
        samples=int(samples),
        hit_rate=float(hit_rate),
        miss_rate=float(miss_rate),
        median_abs_error_m=float(med),
        p90_abs_error_m=float(p90),
        unknown_ray_frac=float(unknown_frac),
        inconsistent=bool(inconsistent),
        suggestions=out_suggestions,
    )
