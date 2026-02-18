from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import numpy as np

from perception.primitive_fit import fit_plane_ransac
from world.occupancy import OCCUPIED


@dataclass
class SceneObject:
    id: str
    type: str  # "plane" (MVP)
    params: Dict[str, Any]
    confidence: float
    status: str  # "TENTATIVE" | "CONFIRMED" | "NEEDS_SCAN"


@dataclass
class SceneGraph:
    objects: Dict[str, SceneObject] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def upsert_plane(self, plane_id: str, fit: dict) -> None:
        # Confidence is a simple function of inlier_ratio and rmse.
        inlier_ratio = float(fit.get("inlier_ratio", 0.0))
        rmse = float(fit.get("rmse", 1e9))
        conf = max(0.0, min(1.0, inlier_ratio * (1.0 / (1.0 + 10.0 * rmse))))
        status = "CONFIRMED" if conf >= 0.4 else "TENTATIVE"
        self.objects[plane_id] = SceneObject(
            id=plane_id,
            type="plane",
            params=fit,
            confidence=float(conf),
            status=status,
        )

    def serialize(self) -> dict:
        return {
            "objects": [
                {
                    "id": o.id,
                    "type": o.type,
                    "params": o.params,
                    "confidence": o.confidence,
                    "status": o.status,
                }
                for o in self.objects.values()
            ],
            "meta": dict(self.meta),
        }


def _occupied_voxel_centers(occupancy, *, max_points: int = 6000, rng_seed: int = 0) -> np.ndarray:
    grid = occupancy.grid
    occ = np.argwhere(grid == OCCUPIED)
    if occ.size == 0:
        return np.empty((0, 3), dtype=np.float32)
    if occ.shape[0] > max_points:
        rng = np.random.default_rng(rng_seed)
        idx = rng.choice(occ.shape[0], size=max_points, replace=False)
        occ = occ[idx]
    # center-of-voxel in world coords
    pts = occupancy.origin[None, :] + (occ.astype(np.float32) + 0.5) * float(occupancy.voxel_size)
    return pts.astype(np.float32)


def update_scene_graph_from_world(scene_graph: SceneGraph, world_model, *, every_n_frames: int = 5) -> Optional[dict]:
    frames = int(world_model.metrics.get("frames", 0))
    if frames <= 0:
        return None
    if every_n_frames > 1 and (frames % every_n_frames) != 0:
        return None

    pts = _occupied_voxel_centers(world_model.occupancy, max_points=6000, rng_seed=frames)
    if pts.shape[0] < 300:
        return None

    fit = fit_plane_ransac(pts, n_iter=250, dist_thresh=0.03, min_inliers=250, rng_seed=frames)
    if not fit:
        return None

    scene_graph.upsert_plane("plane_dominant_0", fit)
    scene_graph.meta["last_plane_fit_frame"] = frames
    return fit
