from __future__ import annotations

import math
import numpy as np


def _plane_from_3pts(a: np.ndarray, b: np.ndarray, c: np.ndarray):
    # returns (n, d) where plane is n·x + d = 0, ||n|| = 1
    ab = b - a
    ac = c - a
    n = np.cross(ab, ac)
    nn = float(np.linalg.norm(n))
    if nn < 1e-9:
        return None
    n = (n / nn).astype(np.float32)
    d = -float(np.dot(n, a))
    return n, d


def fit_plane_ransac(
    points: np.ndarray,
    *,
    n_iter: int = 200,
    dist_thresh: float = 0.02,
    min_inliers: int = 200,
    rng_seed: int = 0,
):
    """
    points: (N,3) float32 world coords
    returns dict or None:
      {"normal":[3], "d":float, "inliers":int, "rmse":float, "inlier_ratio":float}
    """
    if points is None or points.shape[0] < max(3, min_inliers):
        return None
    pts = points.astype(np.float32, copy=False)
    N = int(pts.shape[0])
    rng = np.random.default_rng(rng_seed)

    best = None
    best_inl = 0
    best_rmse = 1e9

    for _ in range(int(n_iter)):
        idx = rng.choice(N, size=3, replace=False)
        model = _plane_from_3pts(pts[idx[0]], pts[idx[1]], pts[idx[2]])
        if model is None:
            continue
        n, d = model
        dist = np.abs(pts @ n + d)
        inliers = dist <= float(dist_thresh)
        inl = int(np.sum(inliers))
        if inl < int(min_inliers):
            continue
        rmse = float(math.sqrt(float(np.mean((dist[inliers]) ** 2))))
        if inl > best_inl or (inl == best_inl and rmse < best_rmse):
            best_inl = inl
            best_rmse = rmse
            best = (n, d, inl, rmse)

    if best is None:
        return None

    n, d, inl, rmse = best
    # Orient normal to have positive Y if possible (assume ARCore-like world: +Y up).
    if float(n[1]) < 0.0:
        n = (-n).astype(np.float32)
        d = -float(d)

    return {
        "normal": [float(n[0]), float(n[1]), float(n[2])],
        "d": float(d),
        "inliers": int(inl),
        "rmse": float(rmse),
        "inlier_ratio": float(inl) / float(N),
    }
