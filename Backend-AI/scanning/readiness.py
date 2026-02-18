from __future__ import annotations

from policy.policy_config import PolicyConfig
from scanning.coverage import compute_work_aabb


def compute_readiness(world_model, anchors: list[dict], policy: PolicyConfig) -> tuple[bool, float, list[str]]:
    """
    STAGE 5: Readiness gating must prevent scaffold requests on weak coverage.
    Rules (MVP):
      - observed_ratio inside work AABB >= threshold
      - unknown near supports <= threshold
      - at least N distinct viewpoints captured (deduped camera positions)
    """
    reasons: list[str] = []

    # Work region stats (preferred) else global stats.
    work = compute_work_aabb(anchors, padding_m=1.25)
    if work:
        box_min, box_max = work
        stats = world_model.occupancy.stats_aabb(box_min, box_max)
        observed_ratio = float(stats["observed_ratio"])
        unknown_ratio = float(stats["unknown_ratio"])
    else:
        stats = world_model.occupancy.stats()
        observed_ratio = float(stats["observed_ratio"])
        unknown_ratio = float(stats["unknown_ratio"])

    if observed_ratio < float(policy.readiness_observed_ratio_min):
        reasons.append(f"LOW_OBSERVED_RATIO:{observed_ratio:.3f}<{float(policy.readiness_observed_ratio_min):.3f}")

    support_points = [a["position"] for a in anchors if a.get("kind") == "support" and a.get("position") is not None]
    near_stats = world_model.occupancy.stats(support_points if support_points else None)
    if support_points and float(near_stats["unknown_ratio"]) > float(policy.unknown_ratio_near_support_max):
        reasons.append(
            f"UNKNOWN_NEAR_SUPPORT:{float(near_stats['unknown_ratio']):.3f}>{float(policy.unknown_ratio_near_support_max):.3f}"
        )

    # View diversity (no silent pass): require at least 3 distinct viewpoints if any anchors exist.
    vp = int(world_model.metrics.get("viewpoints", 0) or 0)
    if anchors and vp < 3:
        reasons.append(f"LOW_VIEW_DIVERSITY:{vp}<3")

    # Score: conservative blend of observed coverage and view diversity.
    cov_score = min(1.0, observed_ratio / max(float(policy.readiness_observed_ratio_min), 1e-6))
    view_score = min(1.0, float(vp) / 3.0) if anchors else 1.0
    score = float(max(0.0, min(1.0, 0.75 * cov_score + 0.25 * view_score)))
    return len(reasons) == 0, score, reasons
