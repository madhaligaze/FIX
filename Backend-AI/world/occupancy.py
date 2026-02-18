from __future__ import annotations

import numpy as np

UNKNOWN = np.uint8(0)
FREE = np.uint8(1)
OCCUPIED = np.uint8(2)


class OccupancyGrid:
    def __init__(self, voxel_size: float, bounds: tuple[float, float] = (-5.0, 5.0)) -> None:
        self.voxel_size = voxel_size
        low, high = bounds
        size = int((high - low) / voxel_size)
        self.origin = np.array([low, low, low], dtype=np.float32)
        self.grid = np.zeros((size, size, size), dtype=np.uint8)

    def _to_idx(self, points: np.ndarray) -> np.ndarray:
        idx = ((points - self.origin) / self.voxel_size).astype(int)
        return idx

    def integrate_depth(self, depth_u16: np.ndarray, intrinsics: dict, pose: dict, depth_scale: float) -> None:
        h, w = depth_u16.shape
        ys = np.arange(0, h, max(1, h // 16))
        xs = np.arange(0, w, max(1, w // 16))
        pts = []
        for y in ys:
            for x in xs:
                d = depth_u16[y, x] * depth_scale
                if d <= 0:
                    continue
                zx = (x - intrinsics["cx"]) * d / intrinsics["fx"]
                zy = (y - intrinsics["cy"]) * d / intrinsics["fy"]
                pts.append([zx, zy, d])
        if not pts:
            return
        pts_np = np.array(pts, dtype=np.float32)
        pos = np.array(pose["position"], dtype=np.float32)
        world_pts = pts_np + pos
        idx = self._to_idx(world_pts)
        valid = np.all((idx >= 0) & (idx < np.array(self.grid.shape)), axis=1)
        idx = idx[valid]
        self.grid[idx[:, 0], idx[:, 1], idx[:, 2]] = OCCUPIED

    def query(self, points: list[list[float]]) -> list[int]:
        pts = np.array(points, dtype=np.float32)
        idx = self._to_idx(pts)
        out = []
        for i in idx:
            if np.any(i < 0) or np.any(i >= np.array(self.grid.shape)):
                out.append(int(UNKNOWN))
            else:
                out.append(int(self.grid[i[0], i[1], i[2]]))
        return out

    def stats(self, target_points: list[list[float]] | None = None) -> dict[str, float]:
        if target_points:
            vals = np.array(self.query(target_points), dtype=np.uint8)
        else:
            vals = self.grid.flatten()
        total = max(1, vals.size)
        unknown = int(np.sum(vals == UNKNOWN))
        observed = int(np.sum(vals != UNKNOWN))
        return {
            "observed_ratio": observed / total,
            "unknown_ratio": unknown / total,
        }
