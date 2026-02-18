from __future__ import annotations

import numpy as np

from world.occupancy import OccupancyGrid


class TSDFVolume:
    def __init__(self, occupancy: OccupancyGrid, truncation: float) -> None:
        self.occupancy = occupancy
        self.truncation = truncation

    def integrate_depth(self, depth_u16: np.ndarray, intrinsics: dict, pose: dict, depth_scale: float) -> None:
        self.occupancy.integrate_depth(depth_u16, intrinsics, pose, depth_scale)

    def extract_mesh(self) -> tuple[np.ndarray, np.ndarray]:
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.int32)
