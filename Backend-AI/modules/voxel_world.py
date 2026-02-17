"""
VoxelWorld — воксельная карта рабочего пространства.
====================================================

Этап 1:
- tri-state мир: UNKNOWN/FREE/OCCUPIED
- depth free-space carving: FREE по лучу, OCCUPIED на поверхности
- консервативные коллизии: UNKNOWN можно считать заблокированным
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Union

import numpy as np


@dataclass
class Obstacle:
    id: str
    type: str
    position: Tuple[float, float, float]
    dimensions: Tuple[float, float, float]


class VoxelCollisionSolver:
    """Compatibility collision solver. Keeps structure unchanged if no precise data."""

    def __init__(self, clearance: float = 0.15):
        self.clearance = clearance

    def resolve_collisions(self, nodes: List[Dict], beams: List[Dict], obstacles: List[Obstacle]):
        return {
            "success": True,
            "nodes": nodes,
            "beams": beams,
            "moved_nodes": 0,
            "removed_beams": 0,
            "obstacles": len(obstacles),
        }


class VoxelWorld:
    """Sparse 3D grid for occupancy/free/unknown queries."""

    UNKNOWN = -1
    FREE = 0
    OCCUPIED = 1

    PIPE = 10
    WALL = 11
    FLOOR = 12

    def __init__(
        self,
        resolution: float = 0.05,
        bounds_min: Tuple[float, float, float] = (-4.0, -4.0, -1.0),
        bounds_max: Tuple[float, float, float] = (4.0, 4.0, 3.0),
    ):
        self.resolution = float(resolution)
        self.bounds_min = tuple(map(float, bounds_min))
        self.bounds_max = tuple(map(float, bounds_max))

        self.occupied: Set[Tuple[int, int, int]] = set()
        self.free: Set[Tuple[int, int, int]] = set()

        self._types: Dict[Tuple[int, int, int], int] = {}
        self._grid: Dict[Tuple[int, int, int], int] = {}
        self._last_depth_stats: Dict[str, float] = {}

    def add_point_cloud(self, points: List[List[float]], vtype: int = OCCUPIED) -> int:
        """Fallback fill: point cloud points become OCCUPIED."""
        count = 0
        for p in points:
            if len(p) < 3:
                continue
            x, y, z = float(p[0]), float(p[1]), float(p[2])
            if z < self.bounds_min[2] - 1.0 or z > self.bounds_max[2] + 30.0:
                continue

            coord = self._to_grid(x, y, z)
            if not self._in_bounds_idx(coord):
                continue

            if coord not in self.occupied:
                self.occupied.add(coord)
                self.free.discard(coord)
                self._types[coord] = vtype
                self._grid[coord] = vtype
                count += 1

        return count

    def mark_box(self, center: Dict, dims: Dict, vtype: int = OCCUPIED) -> int:
        """Fill an approximate box region as OCCUPIED."""
        cx, cy, cz = float(center["x"]), float(center["y"]), float(center["z"])
        hw = float(dims.get("width", 0.2)) / 2
        hd = float(dims.get("depth", 0.2)) / 2
        hh = float(dims.get("height", 0.5)) / 2
        r = self.resolution

        count = 0
        for x in np.arange(cx - hw, cx + hw + r, r):
            for y in np.arange(cy - hd, cy + hd + r, r):
                for z in np.arange(cz - hh, cz + hh + r, r):
                    coord = self._to_grid(x, y, z)
                    if not self._in_bounds_idx(coord):
                        continue
                    if coord not in self.occupied:
                        self.occupied.add(coord)
                        self.free.discard(coord)
                        self._types[coord] = vtype
                        self._grid[coord] = vtype
                        count += 1
        return count

    def ingest_yolo_detections(self, detections: List[Dict], fallback_depth: float = 2.0) -> None:
        """Coarse fill from 2D detections (without true depth)."""
        type_map = {
            "pipe_obstacle": self.PIPE,
            "wall": self.WALL,
            "floor_slab": self.FLOOR,
            "cable_tray": self.PIPE,
            "column": self.OCCUPIED,
        }
        for det in detections:
            pos = det.get("position", {})
            dims = det.get("dimensions", {"width": 0.3, "depth": 0.3, "height": 0.5})
            if not pos:
                continue
            if float(pos.get("z", 0.0) or 0.0) == 0.0:
                pos = {**pos, "z": float(fallback_depth)}
            vtype = type_map.get(det.get("type", ""), self.OCCUPIED)
            self.mark_box(pos, dims, vtype=vtype)

    def ingest_depth_map(
        self,
        depth_bytes: bytes,
        width: int,
        height: int,
        fx: float,
        fy: float,
        cx_px: float,
        cy_px: float,
        camera_pose: List[float],
        depth_scale: float = 1000.0,
        confidence_bytes: Optional[bytes] = None,
        confidence_threshold: int = 1,
        max_range: float = 8.0,
        pixel_step: int = 4,
    ) -> Dict[str, float]:
        """Integrate depth into FREE/OCCUPIED sets."""
        stats = {"samples": 0.0, "occupied_added": 0.0, "free_added": 0.0, "conflicts": 0.0}

        if width <= 0 or height <= 0 or fx <= 0 or fy <= 0:
            self._last_depth_stats = stats
            return stats
        if len(camera_pose) < 7:
            self._last_depth_stats = stats
            return stats
        if len(depth_bytes) < width * height * 2:
            self._last_depth_stats = stats
            return stats

        depth_u16 = np.frombuffer(depth_bytes, dtype=np.uint16).reshape(height, width)
        depth_m = depth_u16.astype(np.float32) / float(depth_scale)

        conf = None
        if confidence_bytes is not None and len(confidence_bytes) >= width * height:
            conf = np.frombuffer(confidence_bytes, dtype=np.uint8).reshape(height, width)

        rot = self._quat_to_rotation(*camera_pose[3:7])
        cam_t = np.array(camera_pose[:3], dtype=np.float32)

        for v in range(0, height, max(1, int(pixel_step))):
            for u in range(0, width, max(1, int(pixel_step))):
                d = float(depth_m[v, u])
                if d <= 0.0 or d > float(max_range):
                    continue
                if conf is not None and int(conf[v, u]) < int(confidence_threshold):
                    continue

                xc = (float(u) - float(cx_px)) * d / float(fx)
                yc = (float(v) - float(cy_px)) * d / float(fy)
                p_world = (rot @ np.array([xc, yc, d], dtype=np.float32)) + cam_t

                if not self._in_bounds_xyz(float(p_world[0]), float(p_world[1]), float(p_world[2])):
                    continue

                stats["samples"] += 1.0

                free_added, conflicts = self._mark_free_ray(cam_t, p_world)
                stats["free_added"] += float(free_added)
                stats["conflicts"] += float(conflicts)

                occ_coord = self._to_grid(float(p_world[0]), float(p_world[1]), float(p_world[2]))
                if occ_coord in self.free:
                    stats["conflicts"] += 1.0
                    self.free.discard(occ_coord)

                if occ_coord not in self.occupied:
                    self.occupied.add(occ_coord)
                    self._types.setdefault(occ_coord, self.OCCUPIED)
                    self._grid[occ_coord] = self._types.get(occ_coord, self.OCCUPIED)
                    stats["occupied_added"] += 1.0

        self._last_depth_stats = stats
        return stats

    def get_last_depth_stats(self) -> Dict[str, float]:
        return dict(self._last_depth_stats or {})

    def get_coverage_metrics(self) -> Dict[str, float]:
        total = float(self._total_voxels_in_bounds())
        known = float(len(self.occupied) + len(self.free))
        unknown = max(0.0, total - known)
        coverage = (known / total) if total > 0 else 0.0
        unknown_pct = (unknown / total) if total > 0 else 1.0
        return {
            "bounds_total_voxels": total,
            "known_voxels": known,
            "unknown_voxels": unknown,
            "coverage": coverage,
            "unknown": unknown_pct,
        }

    def get_quality_metrics(self) -> Dict[str, float]:
        coverage = self.get_coverage_metrics()
        return {
            "coverage_pct": coverage["coverage"],
            "unknown_pct": coverage["unknown"],
            "last_depth_stats": self.get_last_depth_stats(),
            **coverage,
        }

    def is_blocked(
        self,
        start: Union[Tuple[float, float, float], Dict[str, float]],
        end: Union[Tuple[float, float, float], Dict[str, float]],
        clearance: float = 0.05,
        unknown_is_blocked: bool = True,
    ) -> bool:
        """Raymarching collision check; UNKNOWN can be treated as blocked."""
        p1 = np.array(self._as_tuple(start), dtype=float)
        p2 = np.array(self._as_tuple(end), dtype=float)
        dist = float(np.linalg.norm(p2 - p1))

        if dist < self.resolution:
            return False

        steps = max(int(dist / (self.resolution / 2)), 2)
        extra = max(0, int(float(clearance) / self.resolution))

        for i in range(steps + 1):
            t = i / steps
            p = p1 + (p2 - p1) * t
            vx, vy, vz = self._to_grid(float(p[0]), float(p[1]), float(p[2]))
            for dx in range(-extra, extra + 1):
                for dz in range(-extra, extra + 1):
                    check = (vx + dx, vy, vz + dz)

                    if check in self.occupied:
                        vtype = self._types.get(check, self.OCCUPIED)
                        if vtype != self.FLOOR:
                            return True
                        continue

                    if unknown_is_blocked and (check not in self.free):
                        return True

        return False

    def get_state(self, x: float, y: float, z: float) -> int:
        coord = self._to_grid(x, y, z)
        if coord in self.occupied:
            return self.OCCUPIED
        if coord in self.free:
            return self.FREE
        return self.UNKNOWN

    def get_type(self, x: float, y: float, z: float) -> int:
        """Backward-compatible alias."""
        state = self.get_state(x, y, z)
        if state == self.OCCUPIED:
            return self._types.get(self._to_grid(x, y, z), self.OCCUPIED)
        if state == self.FREE:
            return self.FREE
        return self.UNKNOWN

    def get_floor_z(self, x: float, y: float, search_below: float = 5.0) -> Optional[float]:
        vx, vy, vz = self._to_grid(x, y, 0.0)
        end_vi = vz - int(search_below / self.resolution)
        for vi in range(vz, end_vi, -1):
            if self._types.get((vx, vy, vi), self.FREE) == self.FLOOR:
                return vi * self.resolution
        return None

    def clear(self) -> None:
        self.occupied.clear()
        self.free.clear()
        self._types.clear()
        self._grid.clear()
        self._last_depth_stats = {}

    @property
    def total_voxels(self) -> int:
        return len(self.occupied)

    @property
    def total_known_voxels(self) -> int:
        return len(self.occupied) + len(self.free)

    def to_ar_mesh(self) -> Dict:
        voxels = []
        for (vx, vy, vz) in self.occupied:
            voxels.append(
                {
                    "x": vx * self.resolution,
                    "y": vy * self.resolution,
                    "z": vz * self.resolution,
                    "state": "occupied",
                    "type": self._types.get((vx, vy, vz), self.OCCUPIED),
                }
            )
        for (vx, vy, vz) in self.free:
            voxels.append(
                {
                    "x": vx * self.resolution,
                    "y": vy * self.resolution,
                    "z": vz * self.resolution,
                    "state": "free",
                    "type": self.FREE,
                }
            )
        return {
            "voxels": voxels,
            "resolution": self.resolution,
            "bounds": {"min": self.bounds_min, "max": self.bounds_max},
        }

    def _mark_free_ray(self, origin_w: np.ndarray, surface_w: np.ndarray) -> Tuple[int, int]:
        o = origin_w.astype(np.float32)
        s = surface_w.astype(np.float32)
        direction = s - o
        dist = float(np.linalg.norm(direction))
        if dist <= 1e-6:
            return 0, 0

        direction /= dist
        step = self.resolution / 2.0
        n = max(int(dist / step), 1)

        free_added = 0
        conflicts = 0
        for i in range(n):
            p = o + direction * (i * step)
            if not self._in_bounds_xyz(float(p[0]), float(p[1]), float(p[2])):
                continue
            coord = self._to_grid(float(p[0]), float(p[1]), float(p[2]))
            if coord in self.occupied:
                conflicts += 1
                continue
            if coord not in self.free:
                self.free.add(coord)
                free_added += 1
        return free_added, conflicts

    def _to_grid(self, x: float, y: float, z: float) -> Tuple[int, int, int]:
        r = self.resolution
        return (int(math.floor(x / r)), int(math.floor(y / r)), int(math.floor(z / r)))

    def _in_bounds_xyz(self, x: float, y: float, z: float) -> bool:
        return (
            self.bounds_min[0] <= x <= self.bounds_max[0]
            and self.bounds_min[1] <= y <= self.bounds_max[1]
            and self.bounds_min[2] <= z <= self.bounds_max[2]
        )

    def _in_bounds_idx(self, coord: Tuple[int, int, int]) -> bool:
        x, y, z = coord
        mn = self._to_grid(*self.bounds_min)
        mx = self._to_grid(*self.bounds_max)
        return (mn[0] <= x <= mx[0]) and (mn[1] <= y <= mx[1]) and (mn[2] <= z <= mx[2])

    def _total_voxels_in_bounds(self) -> int:
        mn = self._to_grid(*self.bounds_min)
        mx = self._to_grid(*self.bounds_max)
        return (mx[0] - mn[0] + 1) * (mx[1] - mn[1] + 1) * (mx[2] - mn[2] + 1)

    @staticmethod
    def _as_tuple(p: Union[Tuple[float, float, float], Dict[str, float]]) -> Tuple[float, float, float]:
        if isinstance(p, dict):
            return (float(p.get("x", 0.0)), float(p.get("y", 0.0)), float(p.get("z", 0.0)))
        return (float(p[0]), float(p[1]), float(p[2]))

    @staticmethod
    def _quat_to_rotation(qx, qy, qz, qw) -> np.ndarray:
        return np.array(
            [
                [1 - 2 * (qy**2 + qz**2), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
                [2 * (qx * qy + qz * qw), 1 - 2 * (qx**2 + qz**2), 2 * (qy * qz - qx * qw)],
                [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx**2 + qy**2)],
            ]
        )
