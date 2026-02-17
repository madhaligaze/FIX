import base64
import importlib.util
import pathlib
import sys

from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_main_module():
    path = ROOT / "main.py"
    spec = importlib.util.spec_from_file_location("backend_main", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


main_mod = load_main_module()
client = TestClient(main_mod.app)


def _create_session_id() -> str:
    response = client.post("/session/start", json={})
    assert response.status_code == 200
    return response.json()["session_id"]


def _dummy_rgb_base64() -> str:
    # Not a real image - but safe because tests set enable_vision=False.
    return base64.b64encode(b"rgb").decode("ascii")


def test_session_frame_requires_core_fields():
    session_id = _create_session_id()

    payload = {
        "session_id": session_id,
        "frame_id": "f-1",
        "timestamp": 1.0,
        # missing: rgb_base64, size, intrinsics, pose
    }
    response = client.post("/session/frame", json=payload)

    # FastAPI validation happens before endpoint body
    assert response.status_code == 422
    detail = response.json().get("detail", [])
    # ensure at least one of the required fields is reported missing
    missing_fields = {d.get("loc", ["", ""])[-1] for d in detail if isinstance(d, dict)}
    assert "rgb_base64" in missing_fields


def test_session_frame_point_cloud_degraded_mode():
    session_id = _create_session_id()

    payload = {
        "session_id": session_id,
        "frame_id": "f-2",
        "timestamp": 2.0,
        "rgb_base64": _dummy_rgb_base64(),
        "width": 640,
        "height": 480,
        "fx": 500.0,
        "fy": 500.0,
        "cx_px": 320.0,
        "cy_px": 240.0,
        "pose_world_from_camera": [0, 0, 0, 0, 0, 0, 1],
        "point_cloud": [[0.0, 0.0, 1.0], [0.1, 0.1, 1.1]],
        "enable_vision": False,
    }

    frame_response = client.post("/session/frame", json=payload)
    assert frame_response.status_code == 200
    data = frame_response.json()
    assert data["status"] == "processed"
    assert data["session_id"] == session_id
    assert "geometry_stats" in data
    assert data["geometry_stats"].get("voxels_added", 0) >= 1

    lock_response = client.post("/session/lock_world", json={"session_id": session_id})
    assert lock_response.status_code == 200
    lock_data = lock_response.json()
    assert lock_data["status"] == "LOCKED_WORLD"
    assert lock_data["planner_can_run"] is True
    assert isinstance(lock_data["mesh_version"], int)


def test_session_frame_accepts_depth_packet():
    session_id = _create_session_id()

    # 1x1 depth = 1000 (mm) => 1.0m
    depth_u16 = (1000).to_bytes(2, byteorder="little", signed=False)

    payload = {
        "session_id": session_id,
        "frame_id": "f-3",
        "timestamp": 3.0,
        "rgb_base64": _dummy_rgb_base64(),
        "width": 1,
        "height": 1,
        "fx": 500.0,
        "fy": 500.0,
        "cx_px": 0.0,
        "cy_px": 0.0,
        "pose_world_from_camera": [0, 0, 0, 0, 0, 0, 1],
        "depth_base64": base64.b64encode(depth_u16).decode("ascii"),
        "depth_scale": 1000.0,
        "enable_vision": False,
    }

    response = client.post("/session/frame", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    # We should have depth integration stats in geometry_stats
    assert "samples" in data["geometry_stats"]
    assert data["geometry_stats"]["samples"] >= 1.0
