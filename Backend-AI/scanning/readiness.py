from __future__ import annotations

from policy.policy_config import PolicyConfig


def compute_readiness(world_model, anchors: list[dict], policy: PolicyConfig) -> tuple[bool, float, list[str]]:
    stats = world_model.occupancy.stats()
    reasons: list[str] = []
    if stats["observed_ratio"] < policy.readiness_observed_ratio_min:
        reasons.append("LOW_OBSERVED_RATIO")

    support_points = [a["position"] for a in anchors if a.get("kind") == "support"]
    near_stats = world_model.occupancy.stats(support_points if support_points else None)
    if support_points and near_stats["unknown_ratio"] > policy.unknown_ratio_near_support_max:
        reasons.append("UNKNOWN_NEAR_SUPPORT")

    score = min(1.0, stats["observed_ratio"] / max(policy.readiness_observed_ratio_min, 1e-6))
    return len(reasons) == 0, score, reasons
