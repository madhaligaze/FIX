from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def export_occupancy_npz(world_model, out_path: Path) -> dict[str, Any]:
    """
    MVP overlay export for Android:
      - occupancy grid as compressed npz (grid + origin + voxel_size)

    This is intentionally simple and stable.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    occ = world_model.occupancy
    np.savez_compressed(
        str(out_path),
        grid=occ.grid.astype(np.uint8),
        origin=np.asarray(occ.origin, dtype=np.float32),
        voxel_size=np.asarray([float(occ.voxel_size)], dtype=np.float32),
    )
    return {"format": "npz", "path": str(out_path)}


def export_occupancy_slice_png(
    world_model,
    out_path: Path,
    *,
    axis: str = "z",
    frac: float = 0.2,
) -> dict[str, Any] | None:
    """
    Optional quick-look PNG slice. If Pillow is unavailable, return None.
    UNKNOWN=0 (dark), FREE=1 (mid), OCCUPIED=2 (bright).
    """
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None

    occ = world_model.occupancy
    g = occ.grid.astype(np.uint8)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    axis = axis.lower().strip()
    frac = float(np.clip(frac, 0.0, 1.0))

    if axis == "x":
        i = int(frac * max(1, g.shape[0] - 1))
        sl = g[i, :, :]
    elif axis == "y":
        i = int(frac * max(1, g.shape[1] - 1))
        sl = g[:, i, :]
    else:
        i = int(frac * max(1, g.shape[2] - 1))
        sl = g[:, :, i]

    # Map 0/1/2 -> 0/128/255
    img = (sl.astype(np.float32) * 127.5).clip(0, 255).astype(np.uint8)
    pil = Image.fromarray(img, mode="L")
    pil.save(str(out_path))
    return {"format": "png", "path": str(out_path), "axis": axis, "frac": frac}
