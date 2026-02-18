from __future__ import annotations

import numpy as np


def quat_to_rot(q_xyzw: list[float]) -> np.ndarray:
    x, y, z, w = [float(v) for v in q_xyzw]
    n = x * x + y * y + z * z + w * w
    if n <= 0.0:
        return np.eye(3, dtype=np.float32)
    s = 2.0 / n
    xx, yy, zz = x * x * s, y * y * s, z * z * s
    xy, xz, yz = x * y * s, x * z * s, y * z * s
    wx, wy, wz = w * x * s, w * y * s, w * z * s
    return np.array(
        [
            [1.0 - (yy + zz), xy - wz, xz + wy],
            [xy + wz, 1.0 - (xx + zz), yz - wx],
            [xz - wy, yz + wx, 1.0 - (xx + yy)],
        ],
        dtype=np.float32,
    )


def pose_to_matrix(pose: dict) -> np.ndarray:
    pos = np.array(pose.get("position", [0, 0, 0]), dtype=np.float32)
    q = pose.get("quaternion", [0, 0, 0, 1])
    R = quat_to_rot(q)
    T = np.eye(4, dtype=np.float32)
    T[:3, :3] = R
    T[:3, 3] = pos
    return T


def transform_points(T: np.ndarray, pts: np.ndarray) -> np.ndarray:
    if pts.size == 0:
        return pts
    ones = np.ones((pts.shape[0], 1), dtype=np.float32)
    hom = np.concatenate([pts.astype(np.float32), ones], axis=1)
    out = (T @ hom.T).T[:, :3]
    return out.astype(np.float32)
