from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def _pos(e: dict[str, Any]) -> np.ndarray | None:
    pose = e.get("pose") or {}
    p = pose.get("position", pose.get("pos"))
    if isinstance(p, (list, tuple)) and len(p) == 3:
        return np.asarray(p, dtype=np.float32).reshape(3)
    return None


def _type(e: dict[str, Any]) -> str:
    return str(e.get("type") or e.get("kind") or "unknown")


def _iter_segments(elements: list[dict[str, Any]]) -> Iterable[tuple[str, np.ndarray, np.ndarray, dict[str, Any]]]:
    for e in elements:
        t = _type(e)
        p = _pos(e)
        if p is None:
            continue
        dims = e.get("dims") or {}
        if t == "post":
            h = float(dims.get("height_m") or dims.get("height") or dims.get("z") or 0.0)
            if h <= 0:
                continue
            a = p
            b = p + np.asarray([0.0, 0.0, h], dtype=np.float32)
            yield t, a, b, e
        elif t in ("ledger", "brace"):
            a0 = dims.get("a")
            b0 = dims.get("b")
            if isinstance(a0, (list, tuple)) and isinstance(b0, (list, tuple)) and len(a0) == 3 and len(b0) == 3:
                a = np.asarray(a0, dtype=np.float32).reshape(3)
                b = np.asarray(b0, dtype=np.float32).reshape(3)
                yield t, a, b, e
        else:
            yield t, p, p, e


def collision_check(elements: list[dict[str, Any]], world_model, policy) -> tuple[bool, list[dict[str, Any]]]:
    violations: list[dict[str, Any]] = []
    if not elements:
        return False, [{"type": "NO_SCAFFOLD", "msg": "No scaffold elements generated"}]

    min_clear = float(policy.min_clearance_m)
    sample_pts: list[list[float]] = []
    meta: list[dict[str, Any]] = []

    for t, a, b, e in _iter_segments(elements):
        pa = a.tolist()
        pb = b.tolist()
        pm = ((a + b) * 0.5).tolist()
        sample_pts.extend([pa, pm, pb])
        ref = e.get("id") or e.get("name")
        meta.extend(
            [
                {"elem_type": t, "ref": ref, "where": "a"},
                {"elem_type": t, "ref": ref, "where": "m"},
                {"elem_type": t, "ref": ref, "where": "b"},
            ]
        )

    if not sample_pts:
        return False, [{"type": "NO_POINTS", "msg": "No positions to validate"}]

    d = world_model.query_distance(sample_pts)
    for i, dist in enumerate(d):
        if float(dist) < min_clear:
            violations.append(
                {
                    "type": "COLLISION",
                    "at": meta[i],
                    "dist_m": float(dist),
                    "min_clearance_m": min_clear,
                }
            )
    return len(violations) == 0, violations


def stability_rules(elements: list[dict[str, Any]], policy) -> tuple[bool, list[dict[str, Any]]]:
    violations: list[dict[str, Any]] = []
    posts = [e for e in elements if _type(e) == "post"]
    braces = [e for e in elements if _type(e) == "brace"]
    decks = [e for e in elements if _type(e) == "deck"]

    if len(posts) < 4:
        violations.append({"type": "STABILITY_TOO_FEW_POSTS", "count": len(posts), "min": 4})

    if bool(getattr(policy, "stability_require_diagonals", True)) and len(braces) < 2:
        violations.append({"type": "STABILITY_MISSING_BRACES", "count": len(braces), "min": 2})

    for deck in decks:
        pos = _pos(deck)
        z = float((pos if pos is not None else np.zeros(3))[2])
        if z < 0.2:
            violations.append({"type": "DECK_TOO_LOW", "z_m": z})

    return len(violations) == 0, violations


def access_rules(elements: list[dict[str, Any]], policy) -> tuple[bool, list[dict[str, Any]]]:
    del policy
    violations: list[dict[str, Any]] = []
    decks = [e for e in elements if _type(e) == "deck"]
    access = [e for e in elements if _type(e) in ("stair", "ladder")]

    if decks and not access:
        violations.append({"type": "ACCESS_MISSING_STAIRS", "msg": "Deck exists but no stair/ladder element present"})

    return len(violations) == 0, violations


def validate_all(elements: list[dict[str, Any]], world_model, policy) -> tuple[bool, list[dict[str, Any]]]:
    all_violations: list[dict[str, Any]] = []

    ok1, v1 = collision_check(elements, world_model, policy)
    all_violations.extend(v1)

    ok2, v2 = stability_rules(elements, policy)
    all_violations.extend(v2)

    ok3, v3 = access_rules(elements, policy)
    all_violations.extend(v3)

    return (ok1 and ok2 and ok3 and len(all_violations) == 0), all_violations
