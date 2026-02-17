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


def test_session_frame_requires_intrinsics_and_pose():
    session_id = _create_session_id()

    payload = {
        "session_id": session_id,
        "frame_id": "f-1",
        "timestamp": 1.0,
        "point_cloud": [[0.1, 0.2, 1.0]],
    }
    response = client.post("/session/frame", json=payload)

    assert response.status_code == 400
    assert "intrinsics" in response.json()["detail"]


def test_session_frame_point_cloud_degraded_mode_and_lock_world():
    session_id = _create_session_id()

    payload = {
        "session_id": session_id,
        "frame_id": "f-2",
        "timestamp": 2.0,
        "pose_world_from_camera": [0, 0, 0, 0, 0, 0, 1],
        "intrinsics": {
            "fx": 500.0,
            "fy": 500.0,
            "cx": 320.0,
            "cy": 240.0,
            "width": 640,
            "height": 480,
        },
        "point_cloud": [[0.0, 0.0, 1.0], [0.1, 0.1, 1.1]],
    }

    frame_response = client.post("/session/frame", json=payload)
    assert frame_response.status_code == 200
    frame_data = frame_response.json()
    assert frame_data["degraded_mode"] is True
    assert "coverage_pct" in frame_data["current_quality"]
    assert "unknown_pct" in frame_data["current_quality"]
    assert "drift_proxy" in frame_data["current_quality"]

    lock_response = client.post("/session/lock_world", json={"session_id": session_id})
    assert lock_response.status_code == 200
    lock_data = lock_response.json()
    assert lock_data["status"] == "LOCKED_WORLD"
    assert lock_data["planner_can_run"] is True
    assert isinstance(lock_data["mesh_version"], int)


def test_session_frame_accepts_depth_packet():
    session_id = _create_session_id()

    depth_u16 = (1000).to_bytes(2, byteorder="little", signed=False)
    payload = {
        "session_id": session_id,
        "frame_id": "f-3",
        "timestamp": 3.0,
        "pose_world_from_camera": [0, 0, 0, 0, 0, 0, 1],
        "intrinsics": {
            "fx": 500.0,
            "fy": 500.0,
            "cx": 0.0,
            "cy": 0.0,
            "width": 1,
            "height": 1,
        },
        "depth_map_base64": base64.b64encode(depth_u16).decode("ascii"),
        "depth_scale": 1000.0,
    }

    response = client.post("/session/frame", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["degraded_mode"] is False
