import importlib.util
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, rel_path: str):
    path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module  # needed for dataclasses() __module__ resolution
    spec.loader.exec_module(module)
    return module


voxel_mod = load_module("voxel_world", "modules/voxel_world.py")
reproj_mod = load_module("reprojection_check", "modules/reprojection_check.py")

VoxelWorld = voxel_mod.VoxelWorld
check_reprojection = reproj_mod.check_reprojection


def test_reprojection_hits_single_voxel():
    vw = VoxelWorld(resolution=0.1, bounds_min=(-2, -2, -2), bounds_max=(2, 2, 4))
    vw.add_point_cloud([[0.0, 0.0, 1.0]])

    depth = np.zeros((3, 3), dtype=np.float32)
    depth[1, 1] = 1.0

    rep = check_reprojection(
        voxel_world=vw,
        depth_m=depth,
        width=3,
        height=3,
        fx=1.0,
        fy=1.0,
        cx=1.0,
        cy=1.0,
        pose7=[0, 0, 0, 0, 0, 0, 1],
        max_depth=3.0,
        pixel_step=1,
        error_threshold_m=0.3,
        miss_rate_threshold=0.9,
    )

    assert rep.samples == 1
    assert rep.hit_rate > 0.9
    assert rep.median_abs_error_m < 0.25
