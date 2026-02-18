from __future__ import annotations

import numpy as np

from tracking.pose_quality import evaluate_pose_step
from world.esdf import ESDF
from world.occupancy import OccupancyGrid
from world.tsdf_volume import TSDFVolume


class WorldModel:
    def __init__(self, *, voxel_size: float = 0.2, tsdf_trunc: float = 0.4) -> None:
        self.occupancy = OccupancyGrid(voxel_size=voxel_size)
        self.tsdf = None
        try:
            self.tsdf = TSDFVolume(self.occupancy, truncation=tsdf_trunc)
            self.metrics = {
                "frames": 0,
                "tsdf_available": True,
                "tracking_quality": "UNKNOWN",
                "tracking_reasons": [],
                "viewpoints": 0,
                "_viewpoints_q": [],  # internal list of quantized camera positions
                "conflicts": 0,
            }
        except Exception as exc:
            self.tsdf = None
            self.metrics = {
                "frames": 0,
                "tsdf_available": False,
                "tsdf_reason": str(exc),
                "tracking_quality": "UNKNOWN",
                "tracking_reasons": [],
                "viewpoints": 0,
                "_viewpoints_q": [],
                "conflicts": 0,
            }
        self.esdf = ESDF()

    def _update_viewpoints(self, pose: dict) -> None:
        pos = pose.get("position")
        if not (isinstance(pos, (list, tuple)) and len(pos) == 3):
            return
        # quantize to ~35cm grid for uniqueness
        q = [int(round(float(pos[0]) / 0.35)), int(round(float(pos[1]) / 0.35)), int(round(float(pos[2]) / 0.35))]
        lst = self.metrics.get("_viewpoints_q")
        if not isinstance(lst, list):
            lst = []
            self.metrics["_viewpoints_q"] = lst
        if q not in lst:
            lst.append(q)
            self.metrics["viewpoints"] = int(len(lst))

    def update_from_frame(
        self,
        meta: dict,
        rgb_bytes: bytes,
        depth_bytes: bytes | None,
        pointcloud_bytes: bytes | None,
    ) -> None:
        del pointcloud_bytes
        self.metrics["frames"] = int(self.metrics.get("frames", 0)) + 1

        pose = meta.get("pose", {}) or {}

        # STAGE C: pose jump detection
        prev_pose = self.metrics.get("last_pose")
        quality, reasons = evaluate_pose_step(prev_pose, pose)
        if quality != "UNKNOWN":
            self.metrics["tracking_quality"] = quality
            self.metrics["tracking_reasons"] = reasons
        self.metrics["last_pose"] = {"position": pose.get("position"), "quaternion": pose.get("quaternion")}

        # viewpoint count (STAGE D support)
        self._update_viewpoints(pose)

        if self.tsdf is None:
            return

        intr = meta.get("intrinsics", {}) or {}
        depth_meta = meta.get("depth_meta")
        if depth_meta and depth_bytes:
            w = int(depth_meta["width"])
            h = int(depth_meta["height"])
            depth_u16 = np.frombuffer(depth_bytes, dtype=np.uint16).reshape(h, w)
            self.tsdf.integrate_depth(
                depth_u16,
                intr,
                pose,
                float(depth_meta["scale_m_per_unit"]),
                rgb_bytes=rgb_bytes,
            )
            self.esdf.mark_dirty()

        # propagate conflict counter
        self.metrics["conflicts"] = int(getattr(self.occupancy, "conflict_count", 0))

    def query_distance(self, points: list[list[float]]) -> list[float]:
        return self.esdf.query_distance(points, self.occupancy.grid, self.occupancy.origin, self.occupancy.voxel_size)

    def export_env_mesh_obj_bytes(self) -> bytes:
        if self.tsdf is None:
            return b""
        return self.tsdf.extract_mesh_obj_bytes()

    def export_env_mesh_obj(self) -> bytes:
        # Backward-compatible API for existing call sites.
        return self.export_env_mesh_obj_bytes()

    def compute_overlays(self, policy_dict: dict) -> dict:
        # minimal overlays: occupancy summary + policy snapshot + uncertainty stats
        return {
            "occupancy": self.occupancy.stats(),
            "weights_hist": self.occupancy.weight_histogram(),
            "conflicts": int(getattr(self.occupancy, "conflict_count", 0)),
            "policy": policy_dict,
        }

    def serialize_state(self) -> dict:
        # hide internal viewpoint quant list
        m = dict(self.metrics)
        if "_viewpoints_q" in m:
            m.pop("_viewpoints_q", None)
        return {
            "metrics": m,
            "occupancy": self.occupancy.stats(),
            "weights_hist": self.occupancy.weight_histogram(),
            "conflicts": int(getattr(self.occupancy, "conflict_count", 0)),
            "origin": self.occupancy.origin.tolist(),
            "voxel_size": float(self.occupancy.voxel_size),
        }
