from __future__ import annotations

from policy.policy_config import PolicyConfig


def apply_unknown_policy(world_model, anchors: list[dict], policy: PolicyConfig) -> dict:
    support_points = [a["position"] for a in anchors if a.get("kind") == "support"]
    near_stats = world_model.occupancy.stats(support_points if support_points else None)
    violations: list[str] = []
    if (
        policy.unknown_mode == "forbid"
        and near_stats["unknown_ratio"] > policy.unknown_ratio_near_support_max
        and support_points
    ):
        violations.append("UNKNOWN_NEAR_SUPPORT")

    forbidden_regions = []
    if policy.unknown_mode in {"forbid", "buffer"}:
        for p in support_points:
            forbidden_regions.append({"type": "sphere", "center": p, "radius": policy.unknown_buffer_m})
    return {
        "forbidden_regions": forbidden_regions,
        "violations": violations,
        "unknown_summary": near_stats,
    }
