from __future__ import annotations

import time

import numpy as np

from tracking.pose_quality import evaluate_pose_step
from world.esdf import ESDF
from world.occupancy import OccupancyGrid
from world.quality_metrics import compute_quality_metrics
from world.tsdf_volume import TSDFVolume


def _combine_quality(a: str, b: str) -> str:
    order = {"UNKNOWN": 0, "GOOD": 1, "WARN": 2, "BAD": 3}
    ia = int(order.get(str(a), 0))
    ib = int(order.get(str(b), 0))
    inv = {v: k for k, v in order.items()}
    return inv.get(max(ia, ib), "UNKNOWN")


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
                "icp_fitness": None,
                "icp_rmse": None,
                "viewpoints": 0,
                "_viewpoints_q": [],
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
                "icp_fitness": None,
                "icp_rmse": None,
                "viewpoints": 0,
                "_viewpoints_q": [],
                "conflicts": 0,
            }

        self.esdf = ESDF()
        self._pose_history: list[dict[str, float | list[float]]] = []
        self._last_cloud_pts: np.ndarray | None = None

    def _update_viewpoints(self, pose: dict) -> None:
        pos = pose.get("position")
        if not (isinstance(pos, (list, tuple)) and len(pos) == 3):
            return

        q = [
            int(round(float(pos[0]) / 0.35)),
            int(round(float(pos[1]) / 0.35)),
            int(round(float(pos[2]) / 0.35)),
        ]
        lst = self.metrics.get("_viewpoints_q")
        if not isinstance(lst, list):
            lst = []
        self.metrics["_viewpoints_q"] = lst
        if q not in lst:
            lst.append(q)
        self.metrics["viewpoints"] = int(len(lst))

    def _parse_pointcloud_xyz(self, meta: dict, pointcloud_bytes: bytes) -> np.ndarray | None:
        pc_meta = meta.get("pointcloud_meta") or {}
        fmt = str(pc_meta.get("format") or "xyz")
        if fmt != "xyz":
            return None

        try:
            pts = np.frombuffer(pointcloud_bytes, dtype=np.float32)
            if pts.size % 3 != 0:
                return None
            pts = pts.reshape(-1, 3)
            if pts.shape[0] < 50:
                return None
            return pts
        except Exception:
            return None

    def _icp_consistency(
        self,
        prev_pts: np.ndarray,
        curr_pts: np.ndarray,
    ) -> tuple[str, list[str], float | None, float | None]:
        try:
            import open3d as o3d
        except Exception:
            return "UNKNOWN", [], None, None

        def _mk(pts: np.ndarray):
            pc = o3d.geometry.PointCloud()
            pc.points = o3d.utility.Vector3dVector(pts.astype(np.float64, copy=False))
            return pc.voxel_down_sample(voxel_size=0.05)

        if curr_pts.shape[0] > 4000:
            idx = np.random.choice(curr_pts.shape[0], size=4000, replace=False)
            curr_pts = curr_pts[idx]
        if prev_pts.shape[0] > 4000:
            idx = np.random.choice(prev_pts.shape[0], size=4000, replace=False)
            prev_pts = prev_pts[idx]

        src = _mk(prev_pts)
        tgt = _mk(curr_pts)

        try:
            reg = o3d.pipelines.registration.registration_icp(
                src,
                tgt,
                0.15,
                np.eye(4, dtype=np.float64),
                o3d.pipelines.registration.TransformationEstimationPointToPoint(),
            )
            fitness = float(reg.fitness)
            rmse = float(reg.inlier_rmse)
        except Exception:
            return "UNKNOWN", [], None, None

        reasons: list[str] = []
        quality = "GOOD"
        if fitness < 0.25:
            quality = "BAD"
            reasons.append(f"ICP_LOW_FITNESS:{fitness:.3f}")
        elif fitness < 0.45:
            quality = "WARN"
            reasons.append(f"ICP_BORDERLINE_FITNESS:{fitness:.3f}")

        if rmse > 0.07:
            quality = _combine_quality(quality, "BAD")
            reasons.append(f"ICP_HIGH_RMSE:{rmse:.3f}")
        elif rmse > 0.04:
            quality = _combine_quality(quality, "WARN")
            reasons.append(f"ICP_BORDERLINE_RMSE:{rmse:.3f}")

        return quality, reasons, fitness, rmse

    def update_from_frame(
        self,
        meta: dict,
        rgb_bytes: bytes,
        depth_bytes: bytes | None,
        pointcloud_bytes: bytes | None,
    ) -> None:
        del rgb_bytes
        self.metrics["frames"] = int(self.metrics.get("frames", 0)) + 1

        pose = meta.get("pose", {}) or {}
        pos = pose.get("position")
        if isinstance(pos, (list, tuple)) and len(pos) == 3:
            self._pose_history.append(
                {"ts": float(time.time()), "pos": [float(pos[0]), float(pos[1]), float(pos[2])]}
            )
            if len(self._pose_history) > 300:
                self._pose_history = self._pose_history[-300:]

        prev_pose = self.metrics.get("last_pose")
        quality_pose, reasons_pose = evaluate_pose_step(prev_pose, pose)
        if quality_pose != "UNKNOWN":
            self.metrics["tracking_quality"] = quality_pose
            self.metrics["tracking_reasons"] = reasons_pose
        self.metrics["last_pose"] = {
            "position": pose.get("position"),
            "quaternion": pose.get("quaternion"),
        }

        quality_icp = "UNKNOWN"
        reasons_icp: list[str] = []
        if pointcloud_bytes:
            pts = self._parse_pointcloud_xyz(meta, pointcloud_bytes)
            if pts is not None and self._last_cloud_pts is not None:
                quality_icp, reasons_icp, fit, rmse = self._icp_consistency(
                    self._last_cloud_pts, pts
                )
                self.metrics["icp_fitness"] = fit
                self.metrics["icp_rmse"] = rmse
            if pts is not None:
                self._last_cloud_pts = pts

        current_q = str(self.metrics.get("tracking_quality", "UNKNOWN"))
        merged = _combine_quality(current_q, quality_icp)
        if merged != current_q:
            self.metrics["tracking_quality"] = merged
            reasons = list(self.metrics.get("tracking_reasons") or [])
            reasons.extend(reasons_icp)
            self.metrics["tracking_reasons"] = reasons

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
                rgb_bytes=None,
            )
            self.esdf.mark_dirty()

        self.metrics["conflicts"] = int(getattr(self.occupancy, "conflict_count", 0))

    def query_distance(self, points: list[list[float]]) -> list[float]:
        return self.esdf.query_distance(
            points, self.occupancy.grid, self.occupancy.origin, self.occupancy.voxel_size
        )

    def export_env_mesh_obj_bytes(self) -> bytes:
        if self.tsdf is None:
            return b""
        return self.tsdf.extract_mesh_obj_bytes()

    def export_env_mesh_obj(self) -> bytes:
        return self.export_env_mesh_obj_bytes()

    def compute_overlays(self, policy_dict: dict) -> dict:
        qm = compute_quality_metrics(
            self,
            anchors=(
                policy_dict.get("_anchors_for_metrics") if isinstance(policy_dict, dict) else None
            ),
        )
        return {
            "occupancy": self.occupancy.stats(),
            "weights_hist": self.occupancy.weight_histogram(),
            "conflicts": int(getattr(self.occupancy, "conflict_count", 0)),
            "quality_metrics": qm.to_dict(),
            "policy": policy_dict,
        }

    def anchor_view_count(self, anchor_pos: list[float], *, bins_deg: float = 45.0) -> int:
        if not anchor_pos or len(anchor_pos) != 3 or not self._pose_history:
            return 0
        ax, ay, _ = float(anchor_pos[0]), float(anchor_pos[1]), float(anchor_pos[2])
        step = max(5.0, float(bins_deg))
        seen: set[int] = set()
        for ph in self._pose_history:
            p = ph.get("pos") if isinstance(ph, dict) else None
            if not isinstance(p, list) or len(p) != 3:
                continue
            dx = float(p[0]) - ax
            dy = float(p[1]) - ay
            if (dx * dx + dy * dy) < 0.04:
                continue
            az = np.degrees(np.arctan2(dy, dx))
            b = int(np.floor((az + 180.0) / step))
            seen.add(b)
        return int(len(seen))

    def serialize_state(self) -> dict:
        m = dict(self.metrics)
        m.pop("_viewpoints_q", None)
        return {
            "metrics": m,
            "occupancy": self.occupancy.stats(),
            "weights_hist": self.occupancy.weight_histogram(),
            "conflicts": int(getattr(self.occupancy, "conflict_count", 0)),
            "origin": self.occupancy.origin.tolist(),
            "voxel_size": float(self.occupancy.voxel_size),
        }
