from __future__ import annotations

import io
import numpy as np
import open3d as o3d
from PIL import Image

from world.occupancy import OccupancyGrid
from world.transform import pose_to_matrix


class TSDFVolume:
    def __init__(self, occupancy: OccupancyGrid, truncation: float) -> None:
        self.occupancy = occupancy
        self.truncation = float(truncation)
        self._vol = o3d.pipelines.integration.ScalableTSDFVolume(
            voxel_length=float(self.occupancy.voxel_size),
            sdf_trunc=float(self.truncation),
            color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
        )

    def integrate_depth(
        self,
        depth_u16: np.ndarray,
        intrinsics: dict,
        pose: dict,
        depth_scale: float,
        rgb_bytes: bytes | None = None,
    ) -> None:
        # Keep occupancy up to date for readiness + unknown gating.
        self.occupancy.integrate_depth(depth_u16, intrinsics, pose, depth_scale)

        h, w = depth_u16.shape
        depth_m = (depth_u16.astype(np.float32) * float(depth_scale)).astype(np.float32)
        depth_o3d = o3d.geometry.Image(depth_m)

        color_img = None
        if rgb_bytes:
            try:
                pil = Image.open(io.BytesIO(rgb_bytes)).convert("RGB")
                pil = pil.resize((w, h))
                color_np = np.asarray(pil, dtype=np.uint8)
                color_img = o3d.geometry.Image(color_np)
            except Exception:
                color_img = None
        if color_img is None:
            color_img = o3d.geometry.Image(np.zeros((h, w, 3), dtype=np.uint8))

        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            color=color_img,
            depth=depth_o3d,
            depth_scale=1.0,
            depth_trunc=12.0,
            convert_rgb_to_intensity=False,
        )

        intrinsic = o3d.camera.PinholeCameraIntrinsic(
            int(intrinsics["width"]),
            int(intrinsics["height"]),
            float(intrinsics["fx"]),
            float(intrinsics["fy"]),
            float(intrinsics["cx"]),
            float(intrinsics["cy"]),
        )

        # Contract: pose is camera->world. Open3D expects world->camera, so invert.
        T_cw = pose_to_matrix(pose).astype(np.float64)
        T_wc = np.linalg.inv(T_cw)
        self._vol.integrate(rgbd, intrinsic, T_wc)

    def extract_mesh(self) -> tuple[np.ndarray, np.ndarray]:
        mesh = self._vol.extract_triangle_mesh()
        if len(mesh.vertices) == 0 or len(mesh.triangles) == 0:
            return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.int32)
        verts = np.asarray(mesh.vertices, dtype=np.float32)
        tris = np.asarray(mesh.triangles, dtype=np.int32)
        return verts, tris

    def extract_mesh_obj_bytes(self) -> bytes:
        verts, tris = self.extract_mesh()
        if verts.shape[0] == 0 or tris.shape[0] == 0:
            return b""
        lines: list[str] = []
        for v in verts:
            lines.append(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
        for f in tris:  # OBJ is 1-indexed
            lines.append(f"f {int(f[0])+1} {int(f[1])+1} {int(f[2])+1}")
        return ("\n".join(lines) + "\n").encode("utf-8")
