import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.revision_artifacts import artifact_path, save_bytes_artifact, save_json_artifact
from modules.world_snapshot import commit_snapshot, list_snapshots, load_snapshot, restore_voxel_world


class DummyVoxelWorld:
    OCCUPIED = 1
    FREE = 0

    def __init__(self):
        self.resolution = 0.1
        self.bounds_min = (-1.0, -1.0, -1.0)
        self.bounds_max = (1.0, 1.0, 1.0)
        self.occupied = {(0, 0, 0), (1, 0, 0)}
        self.free = {(0, 1, 0)}
        self._grid = {}

    def get_last_depth_stats(self):
        return {"ok": True}


def _install_fake_voxel_world_module():
    fake_mod = types.ModuleType("modules.voxel_world")

    class FakeVoxelWorld:  # noqa: D401 - simple test double
        def __init__(self, resolution=0.05, bounds_min=(-4.0, -4.0, -1.0), bounds_max=(4.0, 4.0, 3.0)):
            self.resolution = resolution
            self.bounds_min = bounds_min
            self.bounds_max = bounds_max
            self.occupied = set()
            self.free = set()

    fake_mod.VoxelWorld = FakeVoxelWorld
    sys.modules["modules.voxel_world"] = fake_mod


def test_commit_list_load_and_restore_snapshot(tmp_path):
    session_payload = {
        "session_id": "session_abc",
        "scene_context": {"all_detected_objects": [{"class": "pipe"}]},
        "frames": [{"id": i} for i in range(100)],
    }
    vw = DummyVoxelWorld()

    ref = commit_snapshot(
        session_id="session_abc",
        session_dict=session_payload,
        voxel_world=vw,
        root_dir=str(tmp_path),
        reason="test",
    )

    assert ref.dir.exists()
    assert ref.meta_path.exists()
    meta = json.loads(ref.meta_path.read_text(encoding="utf-8"))
    assert meta["revision"] == ref.revision
    assert meta["voxel_counts"]["occupied"] == 2

    all_snaps = list_snapshots("session_abc", root_dir=str(tmp_path))
    assert len(all_snaps) == 1
    assert all_snaps[0]["revision"] == ref.revision

    _install_fake_voxel_world_module()
    loaded = load_snapshot("session_abc", ref.revision, root_dir=str(tmp_path))
    assert loaded["voxel_payload"]["occupied"] == [[0, 0, 0], [1, 0, 0]]

    target = DummyVoxelWorld()
    target.occupied = set()
    target.free = set()
    restore_voxel_world(target, loaded["voxel_payload"])
    assert (1, 0, 0) in target.occupied
    assert (0, 1, 0) in target.free


def test_revision_artifacts_are_written_under_revision_dir(tmp_path):
    session_id = "session_art"
    revision = "rev123"

    manifest_path = save_json_artifact(
        session_id=session_id,
        revision=revision,
        name="export_manifest",
        payload={"status": "ok"},
        snapshot_root=str(tmp_path),
    )
    assert pathlib.Path(manifest_path).exists()
    assert f"/{session_id}/{revision}/artifacts/" in manifest_path

    bin_path = save_bytes_artifact(
        session_id=session_id,
        revision=revision,
        filename="bom.csv",
        data=b"a,b\n1,2\n",
        snapshot_root=str(tmp_path),
    )
    assert pathlib.Path(bin_path).read_bytes().startswith(b"a,b")

    expected = artifact_path(
        session_id=session_id,
        revision=revision,
        filename="mesh.gltf",
        snapshot_root=str(tmp_path),
    )
    assert expected.endswith("/artifacts/mesh.gltf")
