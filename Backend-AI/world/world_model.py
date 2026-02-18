from __future__ import annotations

import time
from typing import Any
import numpy as np

from world.esdf import ESDF
from world.occupancy import OccupancyGrid
from world.tsdf_volume import TSDFVolume


class WorldModel:
    def __init__(self, voxel_size: float, tsdf_trunc: float) -> None:
        self.occupancy = OccupancyGrid(voxel_size=voxel_size)
        self.tsdf = TSDFVolume(self.occupancy, truncation=tsdf_trunc)
        self.esdf = ESDF()
        self.metrics: dict[str, Any] = {"frames": 0, "last_update": None}

    def update_from_frame(
        self,
        frame_meta: dict[str, Any],
        rgb: bytes,
        depth_bytes: bytes | None,
        pointcloud_bytes: bytes | None,
    ) -> None:
        if depth_bytes is not None and frame_meta.get("depth_meta"):
            shape = (int(frame_meta["depth_meta"]["height"]), int(frame_meta["depth_meta"]["width"]))
            depth = np.frombuffer(depth_bytes, dtype=np.uint16).reshape(shape)
            self.tsdf.integrate_depth(
                depth,
                frame_meta["intrinsics"],
                frame_meta["pose"],
                float(frame_meta["depth_meta"]["scale_m_per_unit"]),
                rgb_bytes=rgb,
            )
            self.esdf.mark_dirty()
        self.metrics["frames"] += 1
        self.metrics["last_update"] = time.time()

    def query_distance(self, points: list[list[float]]) -> list[float]:
        return self.esdf.query_distance(points, self.occupancy.grid, self.occupancy.origin, self.occupancy.voxel_size)

    def compute_overlays(self, policy: dict[str, Any]) -> dict[str, Any]:
        stats = self.occupancy.stats()
        return {"unknown_summary": stats, "policy": policy}

    def export_env_mesh_obj(self) -> bytes:
        return self.tsdf.extract_mesh_obj_bytes()

    def serialize_state(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics,
            "stats": self.occupancy.stats(),
            "origin": self.occupancy.origin.tolist(),
            "voxel_size": float(self.occupancy.voxel_size),
            "shape": list(self.occupancy.grid.shape),
        }
