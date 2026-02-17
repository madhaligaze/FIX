"""Stage 5 - Reprojection consistency check.

Goal
----
Given an incoming depth frame and the current voxel world, estimate whether
the model agrees with observation. If it does not, produce actionable scan
suggestions (world-space points) instead of silently continuing.

This is intentionally conservative and cheap:
- It raycasts only against OCCUPIED voxels (UNKNOWN is handled as uncertainty).
- It samples depth sparsely (step) to stay real-time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import math
import numpy as np


@dataclass
class ReprojectionResult:
    ok: bool
    sampled: int
    hits: int
    misses: int
    mismatches: int
    median_abs_error_m: float
    p90_abs_error_m: float
    miss_rate: float
    mismatch_rate: float
    suggestions: List[Dict[str, Any]]


def _quat_to_rotation(qx: float, qy: float, qz: float, qw: float) -> np.ndarray:
    # Same convention as in VoxelWorld._quat_to_rotation
    x, y, z, w = qx, qy, qz, qw
    n = x * x + y * y + z * z + w * w
    if n <= 1e-12:
        return np.eye(3, dtype=float)
    s = 2.0 / n
    xx, yy, zz = x * x * s, y * y * s, z * z * s
    xy, xz, yz = x * y * s, x * z * s, y * z * s
    wx, wy, wz = w * x * s, w * y * s, w * z * s
    return np.array(
        [
            [1.0 - (yy + zz), xy - wz, xz + wy],
            [xy + wz, 1.0 - (xx + zz), yz - wx],
            [xz - wy, yz + wx, 1.0 - (xx + yy)],
        ],
        dtype=float,
    )


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    arr = np.array(values, dtype=float)
    return float(np.percentile(arr, p))


def run_reprojection_check(
    voxel_world: Any,
    depth_bytes: bytes,
    width: int,
    height: int,
    fx: float,
    fy: float,
    cx_px: float,
    cy_px: float,
    camera_pose: List[float],
    max_range_m: float = 8.0,
    sample_step_px: int = 12,
    mismatch_thresh_m: float = 0.15,
    max_suggestions: int = 40,
) -> ReprojectionResult:
    """Compare observed depth with expected depth from the voxel model.

    Returns a ReprojectionResult including scan suggestions.
    """
    if voxel_world is None:
        return ReprojectionResult(
            ok=True,
            sampled=0,
            hits=0,
            misses=0,
            mismatches=0,
            median_abs_error_m=0.0,
            p90_abs_error_m=0.0,
            miss_rate=0.0,
            mismatch_rate=0.0,
            suggestions=[],
        )

    if width <= 0 or height <= 0 or fx <= 0 or fy <= 0 or len(camera_pose) < 7:
        return ReprojectionResult(
            ok=True,
            sampled=0,
            hits=0,
            misses=0,
            mismatches=0,
            median_abs_error_m=0.0,
            p90_abs_error_m=0.0,
            miss_rate=0.0,
            mismatch_rate=0.0,
            suggestions=[],
        )

    if len(depth_bytes) < width * height * 2:
        return ReprojectionResult(
            ok=True,
            sampled=0,
            hits=0,
            misses=0,
            mismatches=0,
            median_abs_error_m=0.0,
            p90_abs_error_m=0.0,
            miss_rate=0.0,
            mismatch_rate=0.0,
            suggestions=[],
        )

    depth_mm = np.frombuffer(depth_bytes, dtype=np.uint16).reshape(int(height), int(width))
    depth_m = depth_mm.astype(np.float32) / 1000.0

    tx, ty, tz, qx, qy, qz, qw = [float(x) for x in camera_pose[:7]]
    R = _quat_to_rotation(qx, qy, qz, qw)
    origin_w = np.array([tx, ty, tz], dtype=float)

    errors: List[float] = []
    suggestions: List[Dict[str, Any]] = []

    sampled = 0
    hits = 0
    misses = 0
    mismatches = 0

    step = max(4, int(sample_step_px))

    # Sample a grid of pixels.
    for v in range(0, int(height), step):
        for u in range(0, int(width), step):
            d_obs = float(depth_m[v, u])
            if d_obs <= 0.0 or d_obs > float(max_range_m):
                continue

            # Build a ray in camera coords: z-forward.
            x = (float(u) - float(cx_px)) / float(fx)
            y = (float(v) - float(cy_px)) / float(fy)
            dir_c = np.array([x, y, 1.0], dtype=float)
            nrm = float(np.linalg.norm(dir_c))
            if nrm <= 1e-9:
                continue
            dir_c = dir_c / nrm

            # To world
            dir_w = R @ dir_c
            dir_w_n = float(np.linalg.norm(dir_w))
            if dir_w_n <= 1e-9:
                continue
            dir_w = dir_w / dir_w_n

            d_exp = voxel_world.raycast_distance(
                origin_world=(float(origin_w[0]), float(origin_w[1]), float(origin_w[2])),
                direction_world=(float(dir_w[0]), float(dir_w[1]), float(dir_w[2])),
                max_dist=float(max_range_m),
            )

            sampled += 1

            if d_exp is None:
                # Model has no surface where depth sees one -> missing occupancy.
                misses += 1
                if len(suggestions) < max_suggestions:
                    p = origin_w + dir_w * d_obs
                    suggestions.append(
                        {
                            "point": {"x": float(p[0]), "y": float(p[1]), "z": float(p[2])},
                            "reason": "model_missing",
                            "severity": 1.0,
                        }
                    )
                continue

            hits += 1
            err = abs(float(d_exp) - float(d_obs))
            errors.append(err)

            if err > float(mismatch_thresh_m):
                mismatches += 1
                # Suggest rescan near the observed surface point.
                if len(suggestions) < max_suggestions:
                    p = origin_w + dir_w * d_obs
                    severity = min(1.0, err / max(1e-3, float(mismatch_thresh_m)))
                    suggestions.append(
                        {
                            "point": {"x": float(p[0]), "y": float(p[1]), "z": float(p[2])},
                            "reason": "depth_mismatch",
                            "severity": float(severity),
                        }
                    )

    median_err = _percentile(errors, 50.0)
    p90_err = _percentile(errors, 90.0)

    miss_rate = float(misses) / float(sampled) if sampled > 0 else 0.0
    mismatch_rate = float(mismatches) / float(sampled) if sampled > 0 else 0.0

    ok = True
    # Conservative default thresholds.
    if sampled >= 30 and (miss_rate > 0.25 or mismatch_rate > 0.35 or p90_err > 0.25):
        ok = False

    return ReprojectionResult(
        ok=ok,
        sampled=sampled,
        hits=hits,
        misses=misses,
        mismatches=mismatches,
        median_abs_error_m=float(median_err),
        p90_abs_error_m=float(p90_err),
        miss_rate=miss_rate,
        mismatch_rate=mismatch_rate,
        suggestions=suggestions,
    )


@dataclass
class ReprojectionReport:
    samples: int
    hit_rate: float
    miss_rate: float
    median_abs_error_m: float
    p90_abs_error_m: float
    unknown_ray_frac: float
    inconsistent: bool
    suggestions: List[Dict[str, Any]]

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


def check_reprojection(
    *,
    voxel_world: Any,
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
    """Backward-compatible wrapper around run_reprojection_check."""
    del unknown_sample_step, miss_rate_threshold

    if depth_m is None:
        depth_bytes = b""
    else:
        depth_bytes = (np.clip(depth_m, 0.0, None) * 1000.0).astype(np.uint16).tobytes()

    result = run_reprojection_check(
        voxel_world=voxel_world,
        depth_bytes=depth_bytes,
        width=width,
        height=height,
        fx=fx,
        fy=fy,
        cx_px=cx,
        cy_px=cy,
        camera_pose=pose7,
        max_range_m=max_depth,
        sample_step_px=pixel_step,
        mismatch_thresh_m=error_threshold_m,
    )

    samples = int(result.sampled)
    hit_rate = float(result.hits) / float(samples) if samples > 0 else 0.0
    suggestions: List[Dict[str, Any]] = []
    for s in result.suggestions:
        pt = s.get("point", {}) if isinstance(s, dict) else {}
        suggestions.append(
            {
                "x": float(pt.get("x", 0.0)),
                "y": float(pt.get("y", 0.0)),
                "z": float(pt.get("z", 0.0)),
                "reason": s.get("reason", "") if isinstance(s, dict) else "",
            }
        )

    return ReprojectionReport(
        samples=samples,
        hit_rate=hit_rate,
        miss_rate=float(result.miss_rate),
        median_abs_error_m=float(result.median_abs_error_m),
        p90_abs_error_m=float(result.p90_abs_error_m),
        unknown_ray_frac=0.0,
        inconsistent=not bool(result.ok),
        suggestions=suggestions,
    )
