from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PolicyConfig:
    unknown_mode: str
    unknown_buffer_m: float
    min_clearance_m: float
    readiness_observed_ratio_min: float
    unknown_ratio_near_support_max: float

    @classmethod
    def from_config(cls, config: dict) -> "PolicyConfig":
        policy = config.get("policy", {})
        world = config.get("world", {})
        return cls(
            unknown_mode=policy.get("unknown_mode", "forbid"),
            unknown_buffer_m=float(policy.get("unknown_buffer_m", 0.5)),
            min_clearance_m=float(world.get("min_clearance_m", 0.2)),
            readiness_observed_ratio_min=float(policy.get("readiness_observed_ratio_min", 0.1)),
            unknown_ratio_near_support_max=float(policy.get("unknown_ratio_near_support_max", 0.6)),
        )
