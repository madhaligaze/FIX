import numpy as np

from world.world_model import WorldModel


def test_tsdf_esdf_smoke_identity_pose_plane_depth():
    # Keep it small/fast: we only assert pipeline runs and ESDF is >0 in carved free space.
    world = WorldModel(voxel_size=0.2, tsdf_trunc=0.4)

    intr = {"fx": 100.0, "fy": 100.0, "cx": 1.0, "cy": 1.0, "width": 4, "height": 4}
    pose = {"position": [0.0, 0.0, 0.0], "quaternion": [0.0, 0.0, 0.0, 1.0]}  # camera->world
    depth_meta = {"width": 4, "height": 4, "scale_m_per_unit": 0.001}

    # Constant depth at 1.0m (1000 mm).
    depth_u16 = (np.ones((4, 4), dtype=np.uint16) * 1000).astype(np.uint16)
    depth_bytes = depth_u16.tobytes()

    meta = {
        "session_id": "s",
        "frame_id": "f1",
        "timestamp": 1.0,
        "intrinsics": intr,
        "pose": pose,
        "depth_meta": depth_meta,
    }

    # A few frames are enough to ensure no exceptions and occupancy is updated.
    for i in range(3):
        meta["frame_id"] = f"f{i}"
        world.update_from_frame(meta, rgb=b"", depth_bytes=depth_bytes, pointcloud_bytes=None)

    stats = world.occupancy.stats()
    assert stats["observed_ratio"] > 0.0

    # Query distance at a point expected to be in carved FREE space along camera ray.
    d = world.query_distance([[0.0, 0.0, 0.0]])[0]
    assert d > 0.0

    # Mesh export must be bytes (can be empty if scene is too small - we don't fail on that).
    obj = world.export_env_mesh_obj()
    assert isinstance(obj, (bytes, bytearray))
