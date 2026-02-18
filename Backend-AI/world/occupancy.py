from __future__ import annotations

import numpy as np

from world.transform import pose_to_matrix

UNKNOWN = np.uint8(0)
FREE = np.uint8(1)
OCCUPIED = np.uint8(2)


class OccupancyGrid:
    """
    Conservative occupancy for readiness + collision gating.
    - UNKNOWN default
    - FREE is carved along rays to observed surfaces
    - OCCUPIED at observed surfaces
    """

    def __init__(self, voxel_size: float, bounds: tuple[float, float] = (-5.0, 5.0)) -> None:
        self.voxel_size = float(voxel_size)
        low, high = bounds
        size = int((high - low) / self.voxel_size)
        self.origin = np.array([low, low, low], dtype=np.float32)
        self.grid = np.zeros((size, size, size), dtype=np.uint8)

    def _to_idx(self, points: np.ndarray) -> np.ndarray:
        return ((points - self.origin) / self.voxel_size).astype(np.int32)

    def _mark(self, idx: np.ndarray, value: np.uint8) -> None:
        shp = np.array(self.grid.shape, dtype=np.int32)
        valid = np.all((idx >= 0) & (idx < shp), axis=1)
        if not np.any(valid):
            return
        ii = idx[valid]
        self.grid[ii[:, 0], ii[:, 1], ii[:, 2]] = value

    def integrate_depth(self, depth_u16: np.ndarray, intrinsics: dict, pose: dict, depth_scale: float) -> None:
        h, w = depth_u16.shape
        fx, fy = float(intrinsics["fx"]), float(intrinsics["fy"])
        cx, cy = float(intrinsics["cx"]), float(intrinsics["cy"])

        # Sparse sampling for speed
        step_y = max(1, h // 24)
        step_x = max(1, w // 24)
        ys = np.arange(0, h, step_y, dtype=np.int32)
        xs = np.arange(0, w, step_x, dtype=np.int32)

        T_cw = pose_to_matrix(pose).astype(np.float64)  # camera->world
        R = T_cw[:3, :3]
        t = T_cw[:3, 3]
        cam_o = t.astype(np.float32)

        occ_idx: list[list[int]] = []
        free_idx: list[list[int]] = []

        max_steps = 120  # hard cap per ray
        for yy in ys:
            for xx in xs:
                d_u = int(depth_u16[yy, xx])
                if d_u <= 0:
                    continue
                d = float(d_u) * float(depth_scale)
                if d <= 0.05 or d > 12.0:
                    continue

                # camera point (OpenCV-like): X right, Y down, Z forward
                X = (float(xx) - cx) * d / fx
                Y = (float(yy) - cy) * d / fy
                Z = d
                p_c = np.array([X, Y, Z], dtype=np.float64)
                p_w = (R @ p_c + t).astype(np.float32)

                # Carve FREE along ray (camera origin -> point), OCCUPIED at end
                ray = p_w - cam_o
                L = float(np.linalg.norm(ray))
                if L < 1e-6:
                    continue
                dir_w = ray / L
                step = float(self.voxel_size) * 0.9
                n = min(max_steps, max(1, int(L / step)))
                # free samples exclude endpoint to avoid overwriting OCCUPIED
                for i in range(1, n):
                    q = cam_o + dir_w * (i * step)
                    free_idx.append(self._to_idx(q[None, :]).reshape(3).tolist())
                occ_idx.append(self._to_idx(p_w[None, :]).reshape(3).tolist())

        if free_idx:
            self._mark(np.asarray(free_idx, dtype=np.int32), FREE)
        if occ_idx:
            self._mark(np.asarray(occ_idx, dtype=np.int32), OCCUPIED)

    def query(self, points: list[list[float]]) -> list[int]:
        pts = np.asarray(points, dtype=np.float32)
        idx = self._to_idx(pts)
        shp = np.array(self.grid.shape, dtype=np.int32)
        out: list[int] = []
        for i in idx:
            if np.any(i < 0) or np.any(i >= shp):
                out.append(int(UNKNOWN))
            else:
                out.append(int(self.grid[i[0], i[1], i[2]]))
        return out

    def in_bounds(self, point: list[float] | np.ndarray) -> bool:
        p = np.asarray(point, dtype=np.float32).reshape(3)
        idx = self._to_idx(p[None, :]).reshape(3)
        shp = np.array(self.grid.shape, dtype=np.int32)
        return bool(np.all(idx >= 0) and np.all(idx < shp))

    def stats(self, target_points: list[list[float]] | None = None) -> dict[str, float]:
        if target_points:
            vals = np.asarray(self.query(target_points), dtype=np.uint8)
        else:
            vals = self.grid.reshape(-1)
        total = max(1, int(vals.size))
        unknown = int(np.sum(vals == UNKNOWN))
        observed = int(np.sum(vals != UNKNOWN))
        return {
            "observed_ratio": float(observed) / float(total),
            "unknown_ratio": float(unknown) / float(total),
        }

    def stats_aabb(self, box_min: list[float], box_max: list[float]) -> dict[str, float]:
        """
        Stats inside axis-aligned bounding box in world coords.
        Returns observed_ratio/unknown_ratio and absolute voxel counts.
        """
        bmin = np.asarray(box_min, dtype=np.float32).reshape(3)
        bmax = np.asarray(box_max, dtype=np.float32).reshape(3)
        lo = np.minimum(bmin, bmax)
        hi = np.maximum(bmin, bmax)

        i0 = self._to_idx(lo[None, :]).reshape(3)
        i1 = self._to_idx(hi[None, :]).reshape(3)
        # inclusive->exclusive padding
        i0 = np.maximum(i0, 0)
        i1 = np.minimum(i1 + 1, np.asarray(self.grid.shape, dtype=np.int32))
        if np.any(i1 <= i0):
            return {"observed_ratio": 0.0, "unknown_ratio": 1.0, "vox_total": 0.0, "vox_unknown": 0.0, "vox_observed": 0.0}

        sub = self.grid[i0[0] : i1[0], i0[1] : i1[1], i0[2] : i1[2]].reshape(-1)
        total = int(sub.size)
        if total <= 0:
            return {"observed_ratio": 0.0, "unknown_ratio": 1.0, "vox_total": 0.0, "vox_unknown": 0.0, "vox_observed": 0.0}
        unknown = int(np.sum(sub == UNKNOWN))
        observed = int(np.sum(sub != UNKNOWN))
        return {
            "observed_ratio": float(observed) / float(total),
            "unknown_ratio": float(unknown) / float(total),
            "vox_total": float(total),
            "vox_unknown": float(unknown),
            "vox_observed": float(observed),
        }
