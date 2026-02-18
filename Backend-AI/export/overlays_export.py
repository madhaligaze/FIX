from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import trimesh


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



def _voxel_boxes_glb_bytes(indices: np.ndarray, origin: np.ndarray, voxel_size: float, color_rgba: tuple[int, int, int, int]) -> bytes:
    scene = trimesh.Scene()
    if indices.size == 0:
        return scene.export(file_type="glb")

    rgba = np.asarray(color_rgba, dtype=np.uint8)
    extents = np.array([voxel_size, voxel_size, voxel_size], dtype=np.float32)
    for idx in indices:
        center = origin + (idx.astype(np.float32) + 0.5) * float(voxel_size)
        b = trimesh.creation.box(extents=extents)
        b.apply_translation(center)
        b.visual.vertex_colors = np.tile(rgba, (len(b.vertices), 1))
        scene.add_geometry(b)
    return scene.export(file_type="glb")


def export_unknown_heatmap_glb(world_model, out_path: Path) -> dict[str, Any]:
    from world.occupancy import UNKNOWN

    occ = world_model.occupancy
    grid = occ.grid.astype(np.uint8)
    unknown = grid == UNKNOWN
    # boundary unknown: unknown with at least one known 6-neighbor
    known = ~unknown
    boundary = np.zeros_like(unknown, dtype=bool)
    for axis in range(3):
        boundary |= unknown & np.roll(known, 1, axis=axis)
        boundary |= unknown & np.roll(known, -1, axis=axis)
    boundary[0, :, :] = False
    boundary[-1, :, :] = False
    boundary[:, 0, :] = False
    boundary[:, -1, :] = False
    boundary[:, :, 0] = False
    boundary[:, :, -1] = False

    idx = np.argwhere(boundary)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    glb = _voxel_boxes_glb_bytes(idx, occ.origin.astype(np.float32), float(occ.voxel_size), (54, 124, 255, 130))
    out_path.write_bytes(glb)
    return {"format": "glb", "path": str(out_path).replace('\\', '/'), "count": int(idx.shape[0])}


def export_clearance_violations_glb(world_model, out_path: Path, *, min_clearance_m: float) -> dict[str, Any]:
    occ = world_model.occupancy
    g = occ.grid
    shp = g.shape
    coords = np.indices(shp).reshape(3, -1).T.astype(np.int32)
    pts = occ.origin[None, :] + (coords.astype(np.float32) + 0.5) * float(occ.voxel_size)
    dists = np.asarray(world_model.query_distance(pts.tolist()), dtype=np.float32)
    bad = dists < float(min_clearance_m)
    idx = coords[bad]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    glb = _voxel_boxes_glb_bytes(idx, occ.origin.astype(np.float32), float(occ.voxel_size), (255, 80, 80, 170))
    out_path.write_bytes(glb)
    return {
        "format": "glb",
        "path": str(out_path).replace('\\', '/'),
        "count": int(idx.shape[0]),
        "min_clearance_m": float(min_clearance_m),
    }
