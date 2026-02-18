from __future__ import annotations

import numpy as np

from world.transform import pose_to_matrix, transform_points

UNKNOWN = np.uint8(0)
FREE = np.uint8(1)
OCCUPIED = np.uint8(2)


class OccupancyGrid:
    def __init__(self, voxel_size: float, bounds: tuple[float, float] = (-5.0, 5.0)) -> None:
        self.voxel_size = float(voxel_size)
        low, high = bounds
        size = int((high - low) / self.voxel_size)
        self.origin = np.array([low, low, low], dtype=np.float32)
        self.grid = np.zeros((size, size, size), dtype=np.uint8)

    def _to_idx(self, points: np.ndarray) -> np.ndarray:
        return ((points - self.origin) / self.voxel_size).astype(int)

    def _mark(self, idx: np.ndarray, value: np.uint8) -> None:
        if idx.size == 0:
            return
        shp = np.array(self.grid.shape)
        valid = np.all((idx >= 0) & (idx < shp), axis=1)
        idx = idx[valid]
        if idx.size == 0:
            return
        self.grid[idx[:, 0], idx[:, 1], idx[:, 2]] = value

    def integrate_depth(self, depth_u16: np.ndarray, intrinsics: dict, pose: dict, depth_scale: float) -> None:
        h, w = depth_u16.shape
        step_y = max(1, h // 48)
        step_x = max(1, w // 48)
        ys = np.arange(0, h, step_y)
        xs = np.arange(0, w, step_x)
        cam_pts = []
        for y in ys:
            for x in xs:
                d_m = float(depth_u16[y, x]) * float(depth_scale)
                if d_m <= 0.0:
                    continue
                x_c = (float(x) - float(intrinsics["cx"])) * d_m / float(intrinsics["fx"])
                y_c = (float(y) - float(intrinsics["cy"])) * d_m / float(intrinsics["fy"])
                cam_pts.append([x_c, y_c, d_m])
        if not cam_pts:
            return

        cam_pts_np = np.array(cam_pts, dtype=np.float32)
        T_cw = pose_to_matrix(pose)  # camera->world
        world_pts = transform_points(T_cw, cam_pts_np)

        # Mark occupied at hit points
        occ_idx = self._to_idx(world_pts)
        self._mark(occ_idx, OCCUPIED)

        # Coarse ray carving: mark FREE along ray from camera origin to hit point
        cam_origin = T_cw[:3, 3].astype(np.float32)
        for p in world_pts[:: max(1, world_pts.shape[0] // 512)]:
            v = p - cam_origin
            dist = float(np.linalg.norm(v))
            if dist <= 1e-6:
                continue
            steps = int(max(2, dist / self.voxel_size))
            t_vals = np.linspace(0.05, 0.95, steps, dtype=np.float32)
            pts = cam_origin[None, :] + t_vals[:, None] * v[None, :]
            idx = self._to_idx(pts)
            # do not overwrite occupied
            shp = np.array(self.grid.shape)
            valid = np.all((idx >= 0) & (idx < shp), axis=1)
            idx = idx[valid]
            if idx.size == 0:
                continue
            current = self.grid[idx[:, 0], idx[:, 1], idx[:, 2]]
            free_mask = current != OCCUPIED
            idx = idx[free_mask]
            if idx.size:
                self.grid[idx[:, 0], idx[:, 1], idx[:, 2]] = FREE

    def query(self, points: list[list[float]]) -> list[int]:
        pts = np.array(points, dtype=np.float32)
        idx = self._to_idx(pts)
        out = []
        shp = np.array(self.grid.shape)
        for i in idx:
            if np.any(i < 0) or np.any(i >= shp):
                out.append(int(UNKNOWN))
            else:
                out.append(int(self.grid[i[0], i[1], i[2]]))
        return out

    def stats(self, target_points: list[list[float]] | None = None) -> dict[str, float]:
        if target_points:
            vals = np.array(self.query(target_points), dtype=np.uint8)
        else:
            vals = self.grid.flatten()
        total = max(1, int(vals.size))
        unknown = int(np.sum(vals == UNKNOWN))
        observed = int(np.sum(vals != UNKNOWN))
        occupied = int(np.sum(vals == OCCUPIED))
        free = int(np.sum(vals == FREE))
        return {
            "observed_ratio": observed / total,
            "unknown_ratio": unknown / total,
            "occupied_ratio": occupied / total,
            "free_ratio": free / total,
        }
