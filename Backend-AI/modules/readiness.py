"""Stage 7 - Readiness gating for planning/export.

The main idea:
- The pipeline must be able to say 'not enough information yet' and refuse to
  generate/approve scaffold layouts that depend on uncertain geometry.
- This is implemented as a conservative gate based on:
    1) UNKNOWN ratio inside the target region (target_box)
    2) (optional) reprojection consistency stats from Stage 5

This is not 'AI magic'. It's guardrails that prevent confident nonsense.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass
class ReadinessThresholds:
    max_unknown_ratio: float = 0.45
    max_miss_rate: float = 0.20
    max_mismatch_rate: float = 0.12
    max_median_abs_error_m: float = 0.07


def compute_readiness(
    voxel_world: Any,
    target_center: Tuple[float, float, float],
    target_half_extents: Tuple[float, float, float],
    reprojection: Optional[Dict[str, Any]] = None,
    thresholds: Optional[ReadinessThresholds] = None,
) -> Dict[str, Any]:
    th = thresholds or ReadinessThresholds()

    cx, cy, cz = map(float, target_center)
    hx, hy, hz = map(float, target_half_extents)

    unknown_ratio = None
    if voxel_world is not None:
        try:
            unknown_ratio = float(
                voxel_world.unknown_fraction_in_box(
                    (cx, cy, cz),
                    (hx, hy, hz),
                    sample_step_vox=2,
                )
            )
        except Exception:
            unknown_ratio = None

    reasons = []
    if unknown_ratio is None:
        reasons.append("no_voxel_world")
    elif unknown_ratio > float(th.max_unknown_ratio):
        reasons.append("too_much_unknown")

    # Reprojection (Stage 5) - optional but recommended
    miss_rate = mismatch_rate = median_abs_error_m = None
    if reprojection:
        miss_rate = float(reprojection.get("miss_rate", 0.0))
        mismatch_rate = float(reprojection.get("mismatch_rate", 0.0))
        median_abs_error_m = float(reprojection.get("median_abs_error_m", 0.0))

        if miss_rate > float(th.max_miss_rate):
            reasons.append("reprojection_miss_high")
        if mismatch_rate > float(th.max_mismatch_rate):
            reasons.append("reprojection_mismatch_high")
        if median_abs_error_m > float(th.max_median_abs_error_m):
            reasons.append("reprojection_error_high")

    ready = len(reasons) == 0

    return {
        "ready_to_lock": bool(ready),
        "reasons": reasons,
        "unknown_ratio": unknown_ratio,
        "thresholds": {
            "max_unknown_ratio": float(th.max_unknown_ratio),
            "max_miss_rate": float(th.max_miss_rate),
            "max_mismatch_rate": float(th.max_mismatch_rate),
            "max_median_abs_error_m": float(th.max_median_abs_error_m),
        },
        "reprojection": {
            "miss_rate": miss_rate,
            "mismatch_rate": mismatch_rate,
            "median_abs_error_m": median_abs_error_m,
        }
        if reprojection
        else None,
    }
