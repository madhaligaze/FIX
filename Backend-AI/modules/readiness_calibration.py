import math
from typing import Any, Dict, List


def _percentile(xs: List[float], p: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    if len(ys) == 1:
        return float(ys[0])
    k = (len(ys) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(ys[int(k)])
    d0 = ys[int(f)] * (c - k)
    d1 = ys[int(c)] * (k - f)
    return float(d0 + d1)


def extract_reprojection_metrics_from_frames(frames: List[Dict[str, Any]]) -> List[Dict[str, float]]:
    out: List[Dict[str, float]] = []
    for fr in frames or []:
        qm = fr.get("quality_metrics") or {}
        rep = None
        gs = qm.get("geometry_stats")
        if isinstance(gs, dict):
            rep = gs.get("reprojection")
        if rep is None:
            rep = qm.get("reprojection")
        if not isinstance(rep, dict):
            continue

        item: Dict[str, float] = {}
        for key in ("miss_rate", "mismatch_rate", "median_abs_error_m", "unknown_ratio"):
            if key in rep:
                try:
                    item[key] = float(rep[key])
                except Exception:
                    pass
        if item:
            out.append(item)
    return out


def suggest_thresholds(metrics: List[Dict[str, float]]) -> Dict[str, Any]:
    if not metrics:
        return {
            "max_miss_rate": 0.20,
            "max_mismatch_rate": 0.12,
            "max_median_abs_error_m": 0.07,
            "max_unknown_ratio": 0.45,
            "source": "defaults",
        }

    miss = [m.get("miss_rate", 0.0) for m in metrics]
    mismatch = [m.get("mismatch_rate", 0.0) for m in metrics]
    mae = [m.get("median_abs_error_m", 0.0) for m in metrics]
    unk = [m.get("unknown_ratio", 0.0) for m in metrics]

    return {
        "max_miss_rate": min(0.95, _percentile(miss, 80) * 1.10 + 0.01),
        "max_mismatch_rate": min(0.95, _percentile(mismatch, 80) * 1.10 + 0.01),
        "max_median_abs_error_m": max(0.02, _percentile(mae, 80) * 1.15 + 0.005),
        "max_unknown_ratio": min(0.98, _percentile(unk, 80) * 1.10 + 0.02),
        "source": "calibrated_p80",
        "n": len(metrics),
    }
