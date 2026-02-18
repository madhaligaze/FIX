from __future__ import annotations

import numpy as np

from world.occupancy import OCCUPIED


def collision_check(elements: list[dict], world_model, policy) -> tuple[bool, list[str]]:
    violations: list[str] = []
    for element in elements:
        p = element["pose"]["pos"]
        occ = world_model.occupancy.query([p])[0]
        if occ == int(OCCUPIED):
            violations.append(f"COLLISION:{element['id']}")
    return len(violations) == 0, violations
