from __future__ import annotations

import numpy as np


def quat_to_rot(q: list[float] | np.ndarray) -> np.ndarray:
    """
    q = [x,y,z,w]
    returns 3x3 rotation matrix
    """
    q = np.asarray(q, dtype=np.float64).reshape(4)
    x, y, z, w = q.tolist()
    n = x * x + y * y + z * z + w * w
    if n < 1e-12:
        return np.eye(3, dtype=np.float64)
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
        dtype=np.float64,
    )


def pose_to_matrix(pose: dict) -> np.ndarray:
    """
    Contract: pose is camera->world.
      pose["position"] = [tx,ty,tz]
      pose["quaternion"] = [x,y,z,w]
    """
    t = np.asarray(pose["position"], dtype=np.float64).reshape(3)
    q = pose["quaternion"]
    R = quat_to_rot(q)
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R
    T[:3, 3] = t
    return T
