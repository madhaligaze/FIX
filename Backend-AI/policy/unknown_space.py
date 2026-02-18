from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from trace.decision_trace import add_constraint_eval


@dataclass(frozen=True)
class UnknownPolicyConfig:
    """
    Stage 15: unknown-space policy as a first-class project setting.

    mode:
      - allow  : never gate on unknown (not recommended)
      - forbid : hard fail if unknown fraction above threshold near critical points
      - buffer : allow but require extra clearance away from unknown (conservative)
    """

    mode: str = "buffer"
    forbid_radius_m: float = 0.35
    buffer_radius_m: float = 0.50
    buffer_clearance_m: float = 0.15
    max_unknown_fraction: float = 0.05
    samples_per_region: int = 256

    def validate(self) -> None:
        if self.mode not in ("allow", "forbid", "buffer"):
            raise ValueError(f"unknown_policy.mode must be allow|forbid|buffer, got: {self.mode}")
        for k in ("forbid_radius_m", "buffer_radius_m", "buffer_clearance_m"):
            v = float(getattr(self, k))
            if not math.isfinite(v) or v < 0:
                raise ValueError(f"unknown_policy.{k} must be finite and >= 0, got: {v}")
        if not (0.0 <= float(self.max_unknown_fraction) <= 1.0):
            raise ValueError(
                f"unknown_policy.max_unknown_fraction must be within [0,1], got: {self.max_unknown_fraction}"
            )
        n = int(self.samples_per_region)
        if n <= 0 or n > 100000:
            raise ValueError(f"unknown_policy.samples_per_region must be in 1..100000, got: {n}")


class UnknownSampler:
    """
    Adapter over your world model / occupancy / ESDF.

    Provide a callable that returns one of:
      - "unknown"
      - "free"
      - "occupied"
    """

    def __init__(self, sample_fn: Callable[[tuple[float, float, float]], str]):
        self._sample_fn = sample_fn

    def sample_label(self, p_w: tuple[float, float, float]) -> str:
        v = self._sample_fn(p_w)
        if v not in ("unknown", "free", "occupied"):
            # normalize unknown responses to avoid crashing on custom backends
            return "unknown"
        return v


def _rand_point_in_sphere(center: tuple[float, float, float], radius: float) -> tuple[float, float, float]:
    # Rejection sampling inside unit sphere, then scale.
    # Good enough for policy gating (not used for precision geometry).
    cx, cy, cz = center
    r = float(radius)
    if r <= 0:
        return center
    while True:
        x = random.uniform(-1.0, 1.0)
        y = random.uniform(-1.0, 1.0)
        z = random.uniform(-1.0, 1.0)
        if x * x + y * y + z * z <= 1.0:
            return (cx + x * r, cy + y * r, cz + z * r)


def estimate_unknown_fraction(
    sampler: UnknownSampler,
    *,
    center_w: tuple[float, float, float],
    radius_m: float,
    samples: int,
) -> float:
    if radius_m <= 0 or samples <= 0:
        return 0.0
    unknown = 0
    for _ in range(samples):
        p = _rand_point_in_sphere(center_w, radius_m)
        if sampler.sample_label(p) == "unknown":
            unknown += 1
    return float(unknown) / float(samples)


@dataclass(frozen=True)
class UnknownPolicyDecision:
    ok: bool
    mode: str
    unknown_fraction: float
    radius_m: float
    required_clearance_m: float
    reason: str | None = None


def evaluate_unknown_policy(
    cfg: UnknownPolicyConfig,
    sampler: UnknownSampler,
    *,
    critical_points_w: Iterable[tuple[float, float, float]],
    decision_id: str,
    trace: list[dict[str, Any]] | None = None,
) -> UnknownPolicyDecision:
    """
    Returns a single conservative decision aggregated over all critical points:
      - Forbid: fail if any point exceeds threshold
      - Buffer: ok, but clearance may be increased if unknown exceeds threshold
      - Allow: always ok
    """
    cfg.validate()

    if cfg.mode == "allow":
        return UnknownPolicyDecision(
            ok=True,
            mode=cfg.mode,
            unknown_fraction=0.0,
            radius_m=0.0,
            required_clearance_m=0.0,
            reason="mode=allow",
        )

    if cfg.mode == "forbid":
        radius = float(cfg.forbid_radius_m)
    else:
        radius = float(cfg.buffer_radius_m)

    worst = 0.0
    for pt in critical_points_w:
        frac = estimate_unknown_fraction(
            sampler,
            center_w=pt,
            radius_m=radius,
            samples=int(cfg.samples_per_region),
        )
        worst = max(worst, frac)

    ok = bool(worst <= float(cfg.max_unknown_fraction))
    required_clearance = 0.0
    reason: str | None = None

    if cfg.mode == "forbid":
        if not ok:
            reason = "unknown_fraction_above_threshold"
        else:
            reason = "unknown_ok"
    else:
        # buffer mode
        if not ok:
            required_clearance = float(cfg.buffer_clearance_m)
            reason = "unknown_requires_buffer"
        else:
            reason = "unknown_ok"

    if trace is not None:
        add_constraint_eval(
            trace,
            decision_id=decision_id,
            constraint_id="unknown_space_policy",
            ok=ok if cfg.mode == "forbid" else True,
            reason=reason,
            metrics={
                "mode": cfg.mode,
                "radius_m": radius,
                "worst_unknown_fraction": worst,
                "threshold": float(cfg.max_unknown_fraction),
                "required_clearance_m": required_clearance,
            },
            severity="warning" if (cfg.mode == "forbid" and not ok) else "info",
        )

    # For buffer mode we do not fail; we increase clearance.
    if cfg.mode == "buffer":
        return UnknownPolicyDecision(
            ok=True,
            mode=cfg.mode,
            unknown_fraction=worst,
            radius_m=radius,
            required_clearance_m=required_clearance,
            reason=reason,
        )

    return UnknownPolicyDecision(
        ok=ok,
        mode=cfg.mode,
        unknown_fraction=worst,
        radius_m=radius,
        required_clearance_m=0.0,
        reason=reason,
    )
