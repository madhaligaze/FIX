from __future__ import annotations


def bom_from_elements(elements: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for element in elements:
        t = element.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1
    return {"counts": counts, "total": len(elements)}
